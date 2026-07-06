# SPDX-License-Identifier: AGPL-3.0-or-later
"""Lager 2 — verktygsbryggan (FEATURE-LLM-ENGINE Fas 2).

Exponerar de BEFINTLIGA MCP-verktygen för agentloopen som function-calling-
scheman och kör dem som den inloggade användaren. Bryggan är en VY över
FastMCP-registret — inget verktyg dubbelregistreras, ingen parallell logik:
anropen går genom exakt samma server.py-wrappers som MCP-trafiken, så ACL,
rate-limits, outbox och audit träffas identiskt.

Rollfiltret (Never/Ask/Always, SELF-IMPROVING-SYSTEM §Lånade format):
- **Never**  = verktyget syns inte i schemat för användarens roller.
  Nivån kommer ur förmåge-katalogens needs_role — samma sanning som driver
  upptäckbarheten. Ett verktyg exponeras om NÅGOT synligt projekt ger rollen;
  varje enskilt anrop ACL-prövas ändå per projekt (försvar i djupled —
  schemafiltret är hygien, aldrig enforcement).
- **Ask**    = outbox/bekräftelse, oförändrat i verktygslagret (SAFETY.md).
- **Always** = fritt för rollen.

Identiteten sätts via server._AGENT_USER (contextvar) — ENDAST här, ENDAST
från en autentiserad webbsession, alltid återställd i finally.
"""

from __future__ import annotations

from ..acl import _rank

# Verktyg som aldrig exponeras för agentloopen oavsett roll — samma lista som
# döljer dem för upptäckbarheten (interna/administrativa).
_NEVER_FOR_CHAT: frozenset = frozenset()


def _role_for_tool() -> dict:
    """tool-namn → lägsta roll som krävs, ur förmåge-katalogen (en sanning)."""
    from ..capabilities.registry import all_capabilities

    mapping: dict = {}
    for cap in all_capabilities():
        for tool in cap.tools:
            need = cap.needs_role or "reader"
            # Ett verktyg kan ingå i flera förmågor — den mildaste rollen gäller
            # för synlighet (enforcement per anrop är ändå verktygets egen).
            if tool not in mapping or _rank(need) < _rank(mapping[tool]):
                mapping[tool] = need
    return mapping


class ToolBridge:
    """Vy över FastMCP-registret, buren av en användaridentitet."""

    def __init__(self, user: str, *, _mcp=None, _acl=None, _audit=None):
        self.user = user
        self._mcp_override = _mcp
        self._acl_override = _acl
        self._audit_override = _audit

    # ------------------------------------------------------------------

    def _mcp(self):
        if self._mcp_override is not None:
            return self._mcp_override
        from .. import server

        return server.mcp

    def _acl(self):
        if self._acl_override is not None:
            return self._acl_override
        from ..server import _get_acl

        return _get_acl()

    def _audit(self):
        if self._audit_override is not None:
            return self._audit_override
        from ..web.api.admin_write import _audit

        return _audit()

    def _max_role_rank(self) -> int:
        """Användarens högsta roll över synliga projekt (admin ⇒ owner)."""
        acl = self._acl()
        if getattr(acl, "is_admin", None) and acl.is_admin(self.user):
            return _rank("owner")
        grants = acl.grants(self.user)
        return max((_rank(r) for r in grants.values()), default=-1)

    # ------------------------------------------------------------------

    def schemas(self) -> list:
        """Neutrala function-calling-scheman för verktygen användaren får SE.
        [{name, description, input_schema}] — Never-nivån är bortfiltrerad."""
        role_map = _role_for_tool()
        my_rank = self._max_role_rank()
        out = []
        for tool in self._mcp()._tool_manager.list_tools():
            need = role_map.get(tool.name)
            if need is None or tool.name in _NEVER_FOR_CHAT:
                continue  # okatalogiserat/internt → aldrig i chatten
            if _rank(need) > my_rank:
                continue  # Never för den här användaren
            out.append({
                "name": tool.name,
                "description": tool.description or "",
                "input_schema": getattr(tool, "parameters", None) or {"type": "object"},
            })
        return out

    def call(self, name: str, arguments: dict) -> dict:
        """Kör ett verktyg som self.user genom ordinarie wrapper (full
        enforcement). Returnerar {ok, result|error} — fel saneras till
        typnamn + budskap, aldrig stacktrace till modellen."""
        tools = {t.name: t for t in self._mcp()._tool_manager.list_tools()}
        tool = tools.get(name)
        role_map = _role_for_tool()
        if tool is None or name not in role_map or name in _NEVER_FOR_CHAT:
            return {"ok": False, "error": f"okänt verktyg: {name}"}
        if _rank(role_map[name]) > self._max_role_rank():
            # Never-nivån: syns inte i schemat, och nekas även om modellen
            # gissar namnet (schemafiltret är hygien — detta är grinden).
            return {"ok": False, "error": f"verktyget {name} kräver roll {role_map[name]}"}

        from .identity import AGENT_USER

        token = AGENT_USER.set(self.user)
        try:
            result = tool.fn(**(arguments or {}))
            ok, payload = True, result
        except Exception as exc:
            ok, payload = False, f"{type(exc).__name__}: {exc}"
        finally:
            AGENT_USER.reset(token)

        project = (arguments or {}).get("project", "-")
        try:
            self._audit().log(
                self.user, str(project), f"chat:{name}", ok,
                f"args={sorted((arguments or {}).keys())}",  # nycklar, aldrig värden
            )
        except Exception:
            pass  # audit-fel får aldrig fälla en verktygskörning
        return {"ok": ok, "result": payload} if ok else {"ok": False, "error": payload}
