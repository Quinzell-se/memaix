# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for rules.engine.evaluate."""

from __future__ import annotations

import pytest

from memaix_gateway.acl import Acl
from memaix_gateway.rules.engine import evaluate
from memaix_gateway.rules.store import RulesStore


@pytest.fixture()
def store(tmp_path):
    return RulesStore.for_path(tmp_path / "rules.db")


@pytest.fixture()
def acl():
    return Acl(users={"alice": {"grants": {"proj": "owner"}}}, projects={"proj": {"vault": "/v"}})


def test_matching_rule_runs_its_actions(store, acl):
    calls = []

    def fake_backlog_add(acl_, user, project, **kwargs):
        calls.append(kwargs)
        return {"id": "new-item"}

    store.add_rule(
        "alice", "proj", "New client mail",
        {"type": "mail", "from_contains": "@client.com"},
        [{"type": "backlog_add", "params": {"project": "proj", "title_from": "subject"}}],
    )
    event = {"type": "mail", "project": "proj", "id": "uid-1", "payload": {"from": "a@client.com", "subject": "Help!"}}
    results = evaluate(store, acl, event, tools={"backlog_add": fake_backlog_add})

    assert len(results) == 1
    assert results[0]["ok"] is True
    assert calls[0]["title"] == "Help!"


def test_dedupe_prevents_double_run_for_same_event(store, acl):
    calls = []

    def fake_action(acl_, user, project, **kwargs):
        calls.append(1)
        return {}

    store.add_rule(
        "alice", "proj", "r", {"type": "mail", "from_contains": "@client.com"},
        [{"type": "backlog_add", "params": {"project": "proj", "title_from": "subject"}}],
    )
    event = {"type": "mail", "project": "proj", "id": "uid-1", "payload": {"from": "a@client.com", "subject": "x"}}
    tools = {"backlog_add": fake_action}

    first = evaluate(store, acl, event, tools=tools)
    second = evaluate(store, acl, event, tools=tools)  # e.g. mail-poll saw it again
    assert len(first) == 1
    assert len(second) == 0  # already handled — not re-run
    assert len(calls) == 1


def test_non_matching_rule_is_skipped(store, acl):
    store.add_rule(
        "alice", "proj", "r", {"type": "mail", "from_contains": "@client.com"},
        [{"type": "backlog_add", "params": {"project": "proj", "title_from": "subject"}}],
    )
    event = {"type": "mail", "project": "proj", "id": "uid-2", "payload": {"from": "spam@random.com", "subject": "x"}}
    results = evaluate(store, acl, event, tools={})
    assert results == []


def test_disabled_rule_never_matches(store, acl):
    rule = store.add_rule(
        "alice", "proj", "r", {"type": "mail", "from_contains": "@client.com"}, []
    )
    store.set_enabled(rule["id"], False)
    event = {"type": "mail", "project": "proj", "id": "uid-3", "payload": {"from": "a@client.com"}}
    assert evaluate(store, acl, event, tools={}) == []


def test_one_failing_action_does_not_stop_the_rest(store, acl):
    def boom(acl_, user, project, **kwargs):
        raise RuntimeError("fail")

    def ok_fn(acl_, user, project, **kwargs):
        return {"ok": True}

    store.add_rule(
        "alice", "proj", "r", {"type": "mail", "from_contains": "@client.com"},
        [
            {"type": "backlog_add", "params": {"project": "proj", "title_from": "subject"}},
            {"type": "pm_raid_add", "params": {"project": "proj", "raid_type": "Risk", "summary": "x"}},
        ],
    )
    event = {"type": "mail", "project": "proj", "id": "uid-4", "payload": {"from": "a@client.com", "subject": "s"}}
    results = evaluate(store, acl, event, tools={"backlog_add": boom, "pm_raid_add": ok_fn})
    assert results[0]["ok"] is False  # overall rule marked failed
    assert len(results[0]["actions"]) == 2  # but both actions still ran
    assert results[0]["actions"][1]["ok"] is True


def test_dry_run_never_reserves_so_it_can_be_repeated(store, acl):
    def fake_action(acl_, user, project, **kwargs):
        return {"id": "x"}

    store.add_rule(
        "alice", "proj", "r", {"type": "mail", "from_contains": "@client.com"},
        [{"type": "backlog_add", "params": {"project": "proj", "title_from": "subject"}}],
    )
    event = {"type": "mail", "project": "proj", "id": "uid-5", "payload": {"from": "a@client.com", "subject": "s"}}
    tools = {"backlog_add": fake_action}

    first = evaluate(store, acl, event, tools=tools, dry_run=True)
    second = evaluate(store, acl, event, tools=tools, dry_run=True)
    assert len(first) == 1
    assert len(second) == 1  # dry_run doesn't consume the dedupe slot
    assert first[0]["actions"][0]["dry_run"] is True


def test_evaluate_scopes_to_event_project(store, acl):
    store.add_rule(
        "alice", "other-proj", "r", {"type": "mail", "from_contains": "@client.com"}, []
    )
    event = {"type": "mail", "project": "proj", "id": "uid-6", "payload": {"from": "a@client.com"}}
    assert evaluate(store, acl, event, tools={}) == []


def test_internal_event_triggers_rule():
    """Proves the engine handles internal (non-mail) events identically."""
    from memaix_gateway.rules.store import RulesStore as _RS
    import tempfile
    from pathlib import Path

    store = _RS.for_path(Path(tempfile.mkdtemp()) / "r.db")
    acl_ = Acl(users={"alice": {"grants": {"proj": "owner"}}}, projects={"proj": {"vault": "/v"}})

    store.add_rule(
        "alice", "proj", "on-done",
        {"type": "internal", "event": "backlog.status", "to": "done"},
        [{"type": "notify", "params": {"text": "Item finished!"}}],
    )
    event = {
        "type": "internal", "project": "proj", "id": "backlog-item-1:done",
        "payload": {"event": "backlog.status", "to": "done", "from": "in-dev"},
    }
    results = evaluate(store, acl_, event, tools={"_channels": []})
    assert len(results) == 1
    assert results[0]["actions"][0]["ok"] is True
