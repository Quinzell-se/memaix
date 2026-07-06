# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fas 2 — verktygsbryggan + agentloopen (FEATURE-LLM-ENGINE).

Acceptanskriterierna ur specen, som tester:
- en reader kan inte NÅ skriv-verktyg via chatten (varken schema eller anrop)
- ett scriptat testsamtal ("vad har jag i kalendern?") kör calendar_list som
  RÄTT användare — identiteten sätts och återställs runt varje anrop
- anropen går genom SAMMA funktionsobjekt som MCP (ingen parallell väg —
  det är den arkitektoniska garantin för att outbox/ACL/limits ärvs intakta)
"""

from __future__ import annotations

import pytest

from memaix_gateway.acl import Acl
from memaix_gateway.capabilities.registry import Capability, clear_registry, register
from memaix_gateway.llm.agent import DailyBudget, run_turn
from memaix_gateway.llm.client import LLMError
from memaix_gateway.llm.identity import AGENT_USER
from memaix_gateway.llm.toolbridge import ToolBridge


class _FakeTool:
    def __init__(self, name, fn, description="", parameters=None):
        self.name, self.fn = name, fn
        self.description = description
        self.parameters = parameters or {"type": "object"}


class _FakeToolManager:
    def __init__(self, tools):
        self._tools = tools

    def list_tools(self):
        return self._tools


class _FakeMCP:
    def __init__(self, tools):
        self._tool_manager = _FakeToolManager(tools)


class _Audit:
    def __init__(self):
        self.entries = []

    def log(self, *a):
        self.entries.append(a)


@pytest.fixture()
def rig(monkeypatch):
    clear_registry()
    register(
        Capability(key="cal.view", area="calendar", title_key="t", summary_key="s",
                   tools=("calendar_list",), example_prompts_key="e",
                   needs_role="collaborator", needs_resource="calendar", tags=()),
        Capability(key="mail.send", area="mail", title_key="t2", summary_key="s2",
                   tools=("email_send",), example_prompts_key="e2",
                   needs_role="owner", needs_resource="mailbox", tags=()),
        Capability(key="mem.recall", area="memory", title_key="t3", summary_key="s3",
                   tools=("memory_search",), example_prompts_key="e3",
                   needs_role="reader", needs_resource="vault", tags=()),
    )
    acl = Acl(
        users={
            "jimmy": {"grants": {"acme": "owner"}},
            "rita": {"grants": {"acme": "reader"}},
        },
        projects={"acme": {"vault": "/tmp/v"}},
    )
    seen = {"identity_at_call": None, "sent": []}

    def calendar_list(project: str):
        seen["identity_at_call"] = AGENT_USER.get()
        return [{"title": "standup 09:00", "project": project}]

    def email_send(project: str, to: str, body: str):
        seen["sent"].append(to)
        return {"queued": True}

    def memory_search(project: str, query: str):
        return []

    tools = [
        _FakeTool("calendar_list", calendar_list),
        _FakeTool("email_send", email_send),
        _FakeTool("memory_search", memory_search),
        _FakeTool("internal_secret_tool", lambda: "hemligt"),  # okatalogiserad
    ]
    audit = _Audit()
    mk = lambda user: ToolBridge(user, _mcp=_FakeMCP(tools), _acl=acl, _audit=audit)
    yield mk, seen, audit
    clear_registry()


def test_reader_never_sees_write_tools(rig):
    mk, _, _ = rig
    names = {t["name"] for t in mk("rita").schemas()}
    assert "memory_search" in names, "reader ser läs-verktyg"
    assert "calendar_list" not in names, "collaborator-verktyg är Never för reader"
    assert "email_send" not in names, "owner-verktyg är Never för reader"
    assert "internal_secret_tool" not in names, "okatalogiserat exponeras aldrig"


def test_owner_sees_tools_but_uncataloged_stays_hidden(rig):
    mk, _, _ = rig
    names = {t["name"] for t in mk("jimmy").schemas()}
    assert {"calendar_list", "email_send", "memory_search"} <= names
    assert "internal_secret_tool" not in names


def test_reader_denied_even_when_guessing_tool_name(rig):
    # Schemafiltret är hygien — grinden håller även om modellen gissar namnet.
    mk, seen, _ = rig
    outcome = mk("rita").call("email_send", {"project": "acme", "to": "x@y.se", "body": "hej"})
    assert outcome["ok"] is False and "owner" in outcome["error"]
    assert seen["sent"] == [], "verktygsfunktionen får aldrig ens köras"
    outcome = mk("rita").call("internal_secret_tool", {})
    assert outcome["ok"] is False


def test_call_runs_as_right_user_and_resets_identity(rig):
    mk, seen, audit = rig
    assert AGENT_USER.get() is None
    outcome = mk("jimmy").call("calendar_list", {"project": "acme"})
    assert outcome["ok"] is True
    assert seen["identity_at_call"] == "jimmy", "verktyget kördes som inloggad användare"
    assert AGENT_USER.get() is None, "identiteten återställs alltid"
    user, project, tool, ok, detail = audit.entries[-1]
    assert (user, project, tool, ok) == ("jimmy", "acme", "chat:calendar_list", True)
    assert "acme" not in detail, "audit loggar arg-NYCKLAR, aldrig värden"


def test_identity_reset_even_on_tool_crash(rig):
    mk, _, audit = rig

    def boom(project: str):
        raise RuntimeError("smäll (med hemlig detalj)")

    bridge = ToolBridge("jimmy",
                        _mcp=_FakeMCP([_FakeTool("calendar_list", boom)]),
                        _acl=mk("jimmy")._acl_override, _audit=audit)
    outcome = bridge.call("calendar_list", {"project": "acme"})
    assert outcome["ok"] is False and "RuntimeError" in outcome["error"]
    assert AGENT_USER.get() is None


# ───────────────────────────── agentloopen ──────────────────────────────────


class _ScriptedClient:
    """Leverantörsfri klient: spelar upp förutbestämda svar."""

    supports_tools = True

    def __init__(self, replies):
        self.replies = list(replies)
        self.seen_messages = []

    def complete(self, messages, max_tokens=1024, tools=None):
        self.seen_messages.append(list(messages))
        return self.replies.pop(0)


def _cfg(**limits):
    return {"memaix": {"model": {"provider": "anthropic", "limits": limits}},
            "brand": {"name": "Memaix"}}


def test_scripted_calendar_conversation(rig, tmp_path):
    """Acceptanskriteriet: 'vad har jag i kalendern?' kör calendar_list som
    rätt användare och svaret bygger på verktygsresultatet."""
    mk, seen, _ = rig
    client = _ScriptedClient([
        {"content": None, "usage": 10, "tool_calls": [
            {"id": "c1", "name": "calendar_list", "args": {"project": "acme"}}]},
        {"content": "Du har standup 09:00.", "usage": 20, "tool_calls": []},
    ])
    events = []
    result = run_turn(
        "jimmy", [{"role": "user", "content": "vad har jag i kalendern?"}],
        cfg=_cfg(), client=client, bridge=mk("jimmy"),
        budget=DailyBudget(str(tmp_path / "chat.db")),
        on_event=lambda kind, p: events.append((kind, p)),
    )
    assert result["content"] == "Du har standup 09:00."
    assert result["rounds"] == 2 and result["tool_calls"] == 1
    assert seen["identity_at_call"] == "jimmy"
    assert ("tool_start", {"name": "calendar_list"}) in events
    # verktygsresultatet gick tillbaka som DATA (role=tool), aldrig instruktion
    tool_msgs = [m for m in client.seen_messages[1] if m["role"] == "tool"]
    assert "standup" in tool_msgs[0]["content"]
    # systemprompten bär trappan + otrodd-data-regeln
    system = client.seen_messages[0][0]
    assert system["role"] == "system"
    assert "ALDRIG instruktioner" in system["content"]
    assert "hypotes" in system["content"]


def test_round_cap_fails_closed(rig, tmp_path):
    mk, _, _ = rig
    endless = {"content": None, "usage": 1, "tool_calls": [
        {"id": "x", "name": "calendar_list", "args": {"project": "acme"}}]}
    client = _ScriptedClient([endless] * 5)
    with pytest.raises(LLMError) as exc:
        run_turn("jimmy", [{"role": "user", "content": "loopa"}],
                 cfg=_cfg(max_rounds=3), client=client, bridge=mk("jimmy"),
                 budget=DailyBudget(str(tmp_path / "chat.db")))
    assert "3" in str(exc.value)


def test_daily_budget_blocks_and_persists(rig, tmp_path):
    mk, _, _ = rig
    db = str(tmp_path / "chat.db")
    budget = DailyBudget(db)
    client = _ScriptedClient([{"content": "hej", "usage": 900, "tool_calls": []}])
    run_turn("jimmy", [{"role": "user", "content": "hej"}],
             cfg=_cfg(max_tokens_per_day=1000), client=client, bridge=mk("jimmy"),
             budget=budget)
    # ny instans mot samma fil — räknaren överlever (omstart)
    budget2 = DailyBudget(db)
    assert budget2.spent("jimmy") == 900
    with pytest.raises(LLMError) as exc:
        run_turn("jimmy", [{"role": "user", "content": "igen"}],
                 cfg=_cfg(max_tokens_per_day=500), client=_ScriptedClient([]),
                 bridge=mk("jimmy"), budget=budget2)
    assert "token-tak" in str(exc.value)


def test_toolless_model_warns_and_answers(rig, tmp_path):
    mk, _, _ = rig

    class _NoTools(_ScriptedClient):
        supports_tools = False

    client = _NoTools([{"content": "svar utan verktyg", "usage": 5, "tool_calls": []}])
    events = []
    result = run_turn("jimmy", [{"role": "user", "content": "hej"}],
                      cfg=_cfg(), client=client, bridge=mk("jimmy"),
                      budget=DailyBudget(str(tmp_path / "chat.db")),
                      on_event=lambda k, p: events.append(k))
    assert result["content"] == "svar utan verktyg"
    assert "warning" in events


def test_server_user_respects_agent_identity(monkeypatch):
    """CI-bunden (kräver mcp): _user() läser AGENT_USER före OAuth-vägen."""
    pytest.importorskip("mcp")
    from memaix_gateway import server

    token = AGENT_USER.set("jimmy")
    try:
        assert server._user() == "jimmy"
    finally:
        AGENT_USER.reset(token)


# ─────────────── Granskningsfynd fas 2 (adversariell review) ─────────────────


def test_disabled_user_sees_no_tools_and_is_denied(monkeypatch):
    """Fynd 1: kill-switch måste gälla i bryggan, inte bara vid enforce —
    en avstängd användare får varken se scheman eller nå anrop."""
    clear_registry()
    register(
        Capability(key="mem.recall", area="memory", title_key="t", summary_key="s",
                   tools=("memory_search",), example_prompts_key="e",
                   needs_role="reader", needs_resource="vault", tags=()),
    )
    acl = Acl(
        users={"spärrad": {"grants": {"acme": "owner"}, "disabled": True}},
        projects={"acme": {"vault": "/tmp/v"}},
    )
    tools = [_FakeTool("memory_search", lambda project, query: [])]
    bridge = ToolBridge("spärrad", _mcp=_FakeMCP(tools), _acl=acl, _audit=_Audit())
    assert bridge.schemas() == [], "avstängd ser inga verktyg"
    outcome = bridge.call("memory_search", {"project": "acme", "query": "x"})
    assert outcome["ok"] is False, "avstängd nekas vid grinden"
    clear_registry()


def test_single_turn_cannot_blow_past_daily_cap(rig, tmp_path):
    """Fynd 2: mid-tur-omkontroll — en tur med många rundor stoppas när
    ackumulerad förbrukning når taket, inte först vid bokföring efteråt."""
    mk, _, _ = rig
    heavy = {"content": None, "usage": 300, "tool_calls": [
        {"id": "x", "name": "calendar_list", "args": {"project": "acme"}}]}
    client = _ScriptedClient([heavy] * 8)
    budget = DailyBudget(str(tmp_path / "chat.db"))
    with pytest.raises(LLMError) as exc:
        run_turn("jimmy", [{"role": "user", "content": "loopa dyrt"}],
                 cfg=_cfg(max_rounds=8, max_tokens_per_day=1000),
                 client=client, bridge=mk("jimmy"), budget=budget)
    assert "tak" in str(exc.value)
    # och förbrukningen bokfördes trots avbrottet (ingen gratis-tur)
    assert budget.spent("jimmy") > 0


def test_aborted_turn_still_charges_budget(rig, tmp_path):
    """Round-cap-turen bokför sina tokens (annars kringgås taket via retry)."""
    mk, _, _ = rig
    endless = {"content": None, "usage": 50, "tool_calls": [
        {"id": "x", "name": "calendar_list", "args": {"project": "acme"}}]}
    budget = DailyBudget(str(tmp_path / "chat.db"))
    with pytest.raises(LLMError):
        run_turn("jimmy", [{"role": "user", "content": "loopa"}],
                 cfg=_cfg(max_rounds=3, max_tokens_per_day=100000),
                 client=_ScriptedClient([endless] * 3), bridge=mk("jimmy"), budget=budget)
    assert budget.spent("jimmy") == 150  # 3 rundor × 50
