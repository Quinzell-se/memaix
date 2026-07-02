# SPDX-License-Identifier: AGPL-3.0-or-later
"""MCP server entrypoint — Fas 3: HTTP transport + Hydra token auth.

User identity:
  HTTP mode  — Bearer JWT verified by HydraTokenVerifier, subject mapped via acl.yaml.
  stdio mode — MEMAIX_USER env var (backward-compatible).
Rate limiting: 60 req/min per user, 120 req/min per project.
Audit: every tool call is logged to the audit DB (MEMAIX_AUDIT_DB or /tmp/...).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from . import config
from .acl import Acl, AccessDenied
from .capabilities.catalog import register_defaults as _register_default_capabilities
from .safety.audit import AuditLog
from .safety.rate_limit import rate_limiter as _rate_limiter
from .tools import files as t_files
from .tools import whoami as t_whoami
from .tools import memory as t_memory
from .tools import backlog as t_backlog
from .tools import email as t_email
from .tools import calendar as t_cal
from .tools import account as t_account
from .tools import contacts as t_contacts
from .tools import nc_files as t_nc_files
from .tools import nc_tasks as t_nc_tasks
from .tools import onboarding as t_onboarding
from .tools import pm as t_pm
from .tools import pm_engine as t_pm_engine
from .tools.calendar import CalendarAuthRequired, _PerUserGoogleAdapter, _ICalAdapter, _FreeBusyAdapter

logger = logging.getLogger(__name__)

_acl: Acl | None = None
_audit: AuditLog | None = None
_token_store: "TokenStore | None" = None  # type: ignore[name-defined]
_outbox_queue: "ActionQueue | None" = None  # type: ignore[name-defined]
_timeline_store: "ActionsStore | None" = None  # type: ignore[name-defined]
_search_store: "EmbeddingStore | None" = None  # type: ignore[name-defined]
_search_embedder = None
_search_embedder_loaded = False
_notify_store: "NotifyStore | None" = None  # type: ignore[name-defined]
_rules_store: "RulesStore | None" = None  # type: ignore[name-defined]
_nudge_state: "NudgeState | None" = None  # type: ignore[name-defined]
_pm_store: "PMStore | None" = None  # type: ignore[name-defined]


def _get_acl() -> Acl:
    global _acl
    if _acl is None:
        cfg = config.load()
        _acl = Acl.from_config(cfg["acl"])
    return _acl


def _get_token_store():
    global _token_store
    if _token_store is None:
        from .backends.token_store import TokenStore
        from cryptography.fernet import Fernet
        key_ref = os.environ.get("TOKEN_MASTER_KEY")
        if not key_ref:
            # In HTTP (server) mode an ephemeral key silently discards every
            # linked account on restart and differs per worker — refuse to start
            # unless the operator explicitly opts in. stdio/dev keeps the warn.
            import sys
            http_mode = (
                os.environ.get("MEMAIX_TRANSPORT") == "http" or "--http" in sys.argv
            )
            allow_ephemeral = os.environ.get("MEMAIX_ALLOW_EPHEMERAL_KEY", "").lower() in (
                "1", "true", "yes",
            )
            if http_mode and not allow_ephemeral:
                raise RuntimeError(
                    "TOKEN_MASTER_KEY is required in HTTP mode. Generate one with "
                    "`python -c \"from cryptography.fernet import Fernet; "
                    "print(Fernet.generate_key().decode())\"` and set it in .env, "
                    "or set MEMAIX_ALLOW_EPHEMERAL_KEY=1 to accept per-restart key loss."
                )
            import warnings
            warnings.warn(
                "TOKEN_MASTER_KEY not set — using ephemeral key (tokens lost on restart)",
                RuntimeWarning,
                stacklevel=2,
            )
            key: bytes = Fernet.generate_key()
        else:
            key = key_ref.encode() if isinstance(key_ref, str) else key_ref
        db_path = Path(os.environ.get("MEMAIX_TOKEN_DB", "/tmp/memaix-tokens.db"))
        _token_store = TokenStore.for_path(db_path, key)
    return _token_store


def _get_audit() -> AuditLog:
    global _audit
    if _audit is None:
        db_path = Path(os.environ.get("MEMAIX_AUDIT_DB", "/tmp/memaix-audit.db"))
        _audit = AuditLog.for_path(db_path)
    return _audit


def _get_outbox():
    global _outbox_queue
    if _outbox_queue is None:
        from .outbox.queue import ActionQueue
        db_path = Path(os.environ.get("MEMAIX_OUTBOX_DB", "/tmp/memaix-outbox.db"))
        _outbox_queue = ActionQueue.for_path(db_path)
    return _outbox_queue


def _get_timeline():
    global _timeline_store
    if _timeline_store is None:
        from .timeline.store import ActionsStore
        db_path = Path(os.environ.get("MEMAIX_ACTIONS_DB", "/tmp/memaix-actions.db"))
        _timeline_store = ActionsStore.for_path(db_path)
    return _timeline_store


def _user() -> str:
    # HTTP mode: resolve identity from the OAuth token injected by MCP SDK middleware.
    try:
        from mcp.server.auth.middleware.auth_context import get_access_token
        token = get_access_token()
        if token and token.subject:
            uid = _get_acl().user_by_subject(token.subject)
            if uid:
                return uid
            raise RuntimeError(f"OAuth subject not mapped in acl.yaml: {token.subject!r}")
    except ImportError:
        pass

    # stdio fallback (Fas 1-style, backward-compatible).
    uid = os.environ.get("MEMAIX_USER", "").strip()
    if not uid:
        raise RuntimeError("MEMAIX_USER is not set — cannot identify caller")
    return uid


def _rl(user: str, project: str) -> None:
    """Rate-limit check; raises RuntimeError if exceeded."""
    if not _rate_limiter.check_user(user):
        raise RuntimeError("rate_limited: user quota exceeded")
    if not _rate_limiter.check_project(project):
        raise RuntimeError("rate_limited: project quota exceeded")


def _audited(user: str, project: str, tool: str, fn, *args, **kwargs):
    """Call fn(*args, **kwargs), log result to audit, re-raise on error.

    Every tool call funnels through here (whether via _tool_call or the
    older direct-_audited pattern used by calendar_*), which makes this the
    single choke point for the undo/timeline recording hook below — args is
    always (acl, user, project, *tail) by convention (see FEATURE-UNDO-TIMELINE.md).
    """
    try:
        result = fn(*args, **kwargs)
        _get_audit().log(user, project, tool, True)
        _maybe_record_timeline(user, project, tool, args[3:], kwargs, result)
        _maybe_index_for_search(user, project, tool, args[3:], kwargs, result)
        _maybe_publish_internal_event(user, project, tool, args[3:], kwargs, result)
        return result
    except Exception as exc:
        _get_audit().log(user, project, tool, False, str(exc))
        raise


def _maybe_record_timeline(user: str, project: str, tool: str, tail: tuple, kwargs: dict, result) -> None:
    """Best-effort undo-log recording — must never break the tool call itself."""
    from .timeline.inverse import TOOL_HANDLERS

    handler = TOOL_HANDLERS.get(tool)
    if handler is None:
        return
    if isinstance(result, dict) and result.get("pending"):
        return  # queued for outbox approval — nothing actually happened yet
    try:
        summary_fn, inverse_fn = handler
        summary = summary_fn(tail, kwargs, result)
        inverse = inverse_fn(tail, kwargs, result)
        _get_timeline().record(user, project, tool, summary, inverse)
    except Exception:
        logger.warning("timeline recording failed for tool %r", tool, exc_info=True)


def _index_memory_write(acl, user, project, tail, kwargs, result):
    note, content = tail[0], tail[1]
    return ("memory", note, note, content)


def _index_memory_append(acl, user, project, tail, kwargs, result):
    # Re-read the full note so the index holds current content, not just the
    # newly appended fragment (replace_chunks would otherwise drop the rest).
    note = tail[0]
    try:
        full_content = t_memory.memory_read(acl, user, project, note)["content"]
    except Exception:
        full_content = tail[1]
    return ("memory", note, note, full_content)


def _index_backlog_add(acl, user, project, tail, kwargs, result):
    if not isinstance(result, dict) or not result.get("id"):
        return None
    title, description = tail[0], tail[1]
    return ("backlog", result["id"], title, f"{title}\n{description or ''}")


def _index_files_write(acl, user, project, tail, kwargs, result):
    path, content = tail[0], tail[1]
    return ("file", path, path, content)


def _index_nc_files_write(acl, user, project, tail, kwargs, result):
    # Distinct source_type from local files ("nc_file" vs "file") so a
    # search_all citation tells you unambiguously which backend it lives in.
    path, content = tail[0], tail[1]
    return ("nc_file", path, path, content)


# Search-index coverage is intentionally scoped to the writes named in
# FEATURE-SEMANTIC-SEARCH.md's acceptance criteria (memory_write/append,
# backlog_add, files_write) — field-level backlog edits (score/comment/
# set_status) don't change the searchable text meaningfully enough to
# justify a full item re-read on every call; reindex via search_reindex.
# nc_files_write (FEATURE-NEXTCLOUD-BACKEND.md §4) follows the same rule as
# files_write once it exists.
SEARCH_INDEX_HANDLERS = {
    "memory_write": _index_memory_write,
    "memory_append": _index_memory_append,
    "backlog_add": _index_backlog_add,
    "files_write": _index_files_write,
    "nc_files_write": _index_nc_files_write,
}


def _get_search_store():
    global _search_store
    if _search_store is None:
        from .search.store import EmbeddingStore
        db_path = Path(os.environ.get("MEMAIX_INDEX_DB", "/tmp/memaix-index.db"))
        _search_store = EmbeddingStore.for_path(db_path)
    return _search_store


def _get_search_embedder():
    global _search_embedder, _search_embedder_loaded
    if not _search_embedder_loaded:
        from .search.embedder import make_embedder
        search_cfg = config.load().get("memaix", {}).get("search", {})
        _search_embedder = make_embedder(search_cfg)
        _search_embedder_loaded = True
    return _search_embedder


def _get_notify():
    global _notify_store
    if _notify_store is None:
        from .notify.store import NotifyStore
        db_path = Path(os.environ.get("MEMAIX_NOTIFY_DB", "/tmp/memaix-notify.db"))
        _notify_store = NotifyStore.for_path(db_path)
    return _notify_store


def _brief_tools_for_user() -> dict:
    """Concrete tool functions the BriefBuilder uses to gather content —
    built here (not in notify/brief.py) so that module stays free of any
    server.py/tools.* import at module scope."""

    def calendar_events(acl, u, project, day_start, day_end):
        dav = _resolve_calendar_dav(project, u)
        if dav is None:
            return []
        return t_cal.calendar_list(
            acl, u, project, day_start.isoformat(), day_end.isoformat(), _dav=dav
        )

    return {
        "calendar_events": calendar_events,
        "email_list": t_email.email_list,
        "backlog_list": t_backlog.backlog_list,
        "pm_raid_list": t_pm.pm_raid_list,
    }


def _get_rules():
    global _rules_store
    if _rules_store is None:
        from .rules.store import RulesStore
        db_path = Path(os.environ.get("MEMAIX_RULES_DB", "/tmp/memaix-rules.db"))
        _rules_store = RulesStore.for_path(db_path)
    return _rules_store


def _get_pm():
    global _pm_store
    if _pm_store is None:
        from .pm.store import PMStore
        db_path = Path(os.environ.get("MEMAIX_PM_DB", "/tmp/memaix-pm.db"))
        _pm_store = PMStore.for_path(db_path)
    return _pm_store


def _get_nudge_state():
    global _nudge_state
    if _nudge_state is None:
        from .capabilities.nudges import NudgeState
        db_path = Path(os.environ.get("MEMAIX_NUDGE_DB", "/tmp/memaix-nudges.db"))
        _nudge_state = NudgeState.for_path(db_path)
    return _nudge_state


def _get_accounts(user: str) -> list:
    try:
        return _get_token_store().list_accounts(user)
    except Exception:
        return []


def _translator_for_config(cfg: dict):
    from .i18n import get_translator
    locale = cfg.get("memaix", {}).get("server", {}).get("locale", "en")
    return get_translator(locale)


_LOCK_REASON_KEYS = {
    "no_role": "cap.lock.no_role",
    "no_mailbox": "cap.lock.no_mailbox",
    "no_calendar": "cap.lock.no_calendar",
    "no_vault": "cap.lock.no_vault",
    "no_contacts": "cap.lock.no_contacts",
    "no_files": "cap.lock.no_files",
    "no_tasks": "cap.lock.no_tasks",
    "link_google": "cap.lock.link_google",
    "link_microsoft": "cap.lock.link_microsoft",
}


def _lock_reason_text(t, reason: str) -> str:
    return t(_LOCK_REASON_KEYS.get(reason, reason))


def _capability_summary(cap, t) -> dict:
    return {"key": cap.key, "area": cap.area, "title": t(cap.title_key), "summary": t(cap.summary_key)}


def _capability_detail(cap, t) -> dict:
    detail = _capability_summary(cap, t)
    detail["tools"] = list(cap.tools)
    detail["examples"] = t(cap.example_prompts_key)
    return detail


def _capabilities_data(area: str | None = None) -> dict:
    """ACL/account-filtered capability data for the `capabilities` tool,
    `memaix_help` prompt, and `memaix://capabilities` resource — the single
    place these three surfaces read from (docs/FEATURE-DISCOVERABILITY.md §6)."""
    from .capabilities.registry import available_for, group_by_area

    user = _user()
    acl = _get_acl()
    cfg = config.load()
    t = _translator_for_config(cfg)
    available, locked = available_for(acl, user, _get_accounts(user), cfg)

    if area is None:
        grouped = group_by_area(available)
        areas = [
            {"area": a, "capabilities": [_capability_summary(c, t) for c in caps]}
            for a, caps in grouped.items()
        ]
        locked_out = [
            {
                "area": entry["capability"].area,
                "title": t(entry["capability"].title_key),
                "reason": entry["reason"],
                "hint": _lock_reason_text(t, entry["reason"]),
            }
            for entry in locked
        ]
        return {"areas": areas, "locked": locked_out}

    return {
        "area": area,
        "capabilities": [_capability_detail(c, t) for c in available if c.area == area],
        "locked": [
            {
                "title": t(entry["capability"].title_key),
                "reason": entry["reason"],
                "hint": _lock_reason_text(t, entry["reason"]),
            }
            for entry in locked
            if entry["capability"].area == area
        ],
    }


def _index_internal_event_backlog_set_status(tail, kwargs, result):
    # tail = (id, status, expected_version) — see backlog_set_status's _tool_call site.
    if not isinstance(result, dict) or result.get("conflict"):
        return None  # nothing actually transitioned
    item_id, new_status, expected_version = tail[0], tail[1], tail[2]
    return {
        "event_key": f"{item_id}:{expected_version}:{new_status}",
        "payload": {"event": "backlog.status", "to": new_status, "item_id": item_id},
    }


# Internal event sources are intentionally scoped to backlog status
# transitions for v1 — the one already flowing through _audited with a
# reliable pre/post signal. Live mail-poll and schedule-cron trigger sources
# are documented follow-up work (FEATURE-AUTOMATION-RULES.md "Framtida arbete").
INTERNAL_EVENT_HANDLERS = {
    "backlog_set_status": _index_internal_event_backlog_set_status,
}


def _maybe_publish_internal_event(user: str, project: str, tool: str, tail: tuple, kwargs: dict, result) -> None:
    """Best-effort internal-trigger publication — must never break the tool call itself."""
    handler = INTERNAL_EVENT_HANDLERS.get(tool)
    if handler is None:
        return
    try:
        built = handler(tail, kwargs, result)
        if built is None:
            return
        event = {"type": "internal", "project": project, "id": built["event_key"], "payload": built["payload"]}
        from .rules.engine import evaluate
        evaluate(_get_rules(), _get_acl(), event)
    except Exception:
        logger.warning("internal event publish failed for tool %r", tool, exc_info=True)


def _maybe_index_for_search(user: str, project: str, tool: str, tail: tuple, kwargs: dict, result) -> None:
    """Best-effort search-index update — must never break the tool call itself."""
    handler = SEARCH_INDEX_HANDLERS.get(tool)
    if handler is None:
        return
    try:
        acl = _get_acl()
        built = handler(acl, user, project, tail, kwargs, result)
        if built is None:
            return
        source_type, ref, title, text = built
        from .search.index import index_upsert
        index_upsert(_get_search_store(), _get_search_embedder(), project, source_type, ref, title, text)
    except Exception:
        logger.warning("search indexing failed for tool %r", tool, exc_info=True)


def _tool_call(tool: str, project: str, fn, *tail, need: str | None = None, **kwargs):
    """Single entry point for a project-scoped tool call.

    Resolves the caller's identity, applies rate limiting, optionally enforces
    an ACL role, and audit-logs the outcome — the four steps every tool must
    perform.  ``fn`` is invoked as ``fn(acl, user, project, *tail, **kwargs)``,
    which is the shared signature of the tools.* functions.

    Most tools leave ``need`` as None because the underlying tools.* function
    performs its own ``acl.enforce``; pass ``need`` only for tools that gate
    at this layer.
    """
    user = _user()
    _rl(user, project)
    acl = _get_acl()
    if need is not None:
        acl.enforce(user, project, need)
    return _audited(user, project, tool, fn, acl, user, project, *tail, **kwargs)


mcp = FastMCP("memaix")

# Populate the capability registry (docs/FEATURE-DISCOVERABILITY.md) once at
# import time so onboarding/help/board surfaces always reflect the tools
# actually registered below.
_register_default_capabilities()


def all_tool_names() -> set[str]:
    """Return every MCP tool name registered on `mcp` — used by the anti-drift
    capability-coverage test (tests/test_capabilities_coverage.py) so a tool
    can never be added without being made discoverable or explicitly marked
    internal."""
    return {t.name for t in mcp._tool_manager.list_tools()}


# ------------------------------------------------------------------
# Fas 1 tools (unchanged)
# ------------------------------------------------------------------


@mcp.tool()
def whoami() -> dict:
    """Return the calling user's identity and project grants."""
    user = _user()
    acl = _get_acl()
    shared_vault = acl.resource("shared", "vault")
    vault_path = Path(shared_vault) if shared_vault else None
    return t_whoami.whoami(acl, user, vault=vault_path)


@mcp.prompt()
def onboarding_interview() -> str:
    """Run the new-user onboarding interview and store the resulting profile."""
    user = _user()
    cfg = config.load()
    shared_vault = _get_acl().resource("shared", "vault")
    vault = Path(shared_vault) if shared_vault else None
    return t_onboarding.build_interview_prompt(user, vault, cfg)


@mcp.tool()
def onboarding_complete(profile_content: str) -> dict:
    """Store the compiled onboarding profile and mark onboarding done."""
    user = _user()
    _rl(user, "shared")
    shared_vault = _get_acl().resource("shared", "vault")
    if not shared_vault:
        raise RuntimeError("shared vault not configured")
    result = _audited(
        user, "shared", "onboarding_complete",
        t_onboarding.complete_onboarding, user, Path(shared_vault), profile_content,
    )
    result["tour"] = _build_tour_for_user(user, profile_content)
    return result


def _build_tour_for_user(user: str, profile_text: str) -> dict:
    """Rank the user's now-available capabilities against their profile text
    and return a short guided tour — see docs/FEATURE-DISCOVERABILITY.md §5."""
    from .capabilities.registry import available_for

    cfg = config.load()
    t = _translator_for_config(cfg)
    available, _locked = available_for(_get_acl(), user, _get_accounts(user), cfg)
    return t_onboarding.build_tour(user, profile_text, available, t)


@mcp.tool()
def account_link(provider: str) -> dict:
    """Get an OAuth link URL to connect your account."""
    user = _user()
    cfg = config.load()
    public_url = cfg.get("memaix", {}).get("server", {}).get("public_url", "http://localhost:8080")
    return t_account.account_link(_get_acl(), user, provider, public_url)


@mcp.tool()
def account_list() -> list:
    """List your linked OAuth accounts."""
    user = _user()
    store = _get_token_store()
    return t_account.account_list(_get_acl(), user, store)


@mcp.tool()
def account_unlink(provider: str, account: str) -> dict:
    """Unlink an OAuth account."""
    user = _user()
    store = _get_token_store()
    return t_account.account_unlink(_get_acl(), user, provider, account, store)


# ------------------------------------------------------------------
# Outbox tools — approve/reject queued outgoing actions (SAFETY: FEATURE-APPROVAL-OUTBOX.md)
# ------------------------------------------------------------------

# Approving/rejecting a queued action requires the same role the underlying
# tool itself enforces — a reader must never be able to approve an email_send.
_OUTBOX_APPROVAL_ROLE: dict[str, str] = {
    "email_send": "owner",
    "calendar_create": "collaborator",
    "calendar_update": "collaborator",
}


def _outbox_action_or_404(outbox, action_id: str) -> dict:
    action = outbox.get(action_id)
    if action is None:
        raise FileNotFoundError(f"no such outbox action: {action_id!r}")
    return action


@mcp.tool()
def outbox_list(project: str | None = None, status: str = "pending") -> list:
    """List queued outgoing actions (default: pending) for your visible projects."""
    user = _user()
    acl = _get_acl()
    visible = set(acl.visible_projects(user))
    projects = [project] if project else sorted(visible)
    projects = [p for p in projects if p in visible]
    return _get_outbox().list(projects, status or None)


@mcp.tool()
def outbox_get(action_id: str) -> dict:
    """Fetch a single queued action by id."""
    user = _user()
    acl = _get_acl()
    outbox = _get_outbox()
    action = _outbox_action_or_404(outbox, action_id)
    if action["project"] not in acl.visible_projects(user):
        raise AccessDenied(f"{user} cannot see outbox actions for {action['project']}")
    return action


@mcp.tool()
def outbox_approve(action_id: str) -> dict:
    """Approve a queued action and execute it now (requires the tool's own role)."""
    user = _user()
    acl = _get_acl()
    outbox = _get_outbox()
    action = _outbox_action_or_404(outbox, action_id)
    need = _OUTBOX_APPROVAL_ROLE.get(action["tool"], "owner")
    acl.enforce(user, action["project"], need)

    claimed = outbox.claim_for_decision(action_id, "approved", user)
    if claimed is None:
        current = outbox.get(action_id) or {}
        return {"conflict": True, "current_status": current.get("status")}

    from .outbox.execute import execute_pending
    result = execute_pending(acl, claimed)
    ok = "error" not in result
    outbox.record_result(action_id, "executed" if ok else "failed", result)
    _get_audit().log(
        user, action["project"], f"outbox_execute:{action['tool']}", ok,
        "" if ok else str(result.get("error", "")),
    )
    return {"ok": ok, "action_id": action_id, "result": result}


@mcp.tool()
def outbox_reject(action_id: str, reason: str = "") -> dict:
    """Reject a queued action — it is never executed."""
    user = _user()
    acl = _get_acl()
    outbox = _get_outbox()
    action = _outbox_action_or_404(outbox, action_id)
    need = _OUTBOX_APPROVAL_ROLE.get(action["tool"], "owner")
    acl.enforce(user, action["project"], need)

    claimed = outbox.claim_for_decision(action_id, "rejected", user, reason)
    if claimed is None:
        current = outbox.get(action_id) or {}
        return {"conflict": True, "current_status": current.get("status")}

    _get_audit().log(user, action["project"], f"outbox_reject:{action['tool']}", True, reason)
    return {"ok": True, "action_id": action_id, "status": "rejected"}


# ------------------------------------------------------------------
# Timeline tools — undo a recorded action (FEATURE-UNDO-TIMELINE.md)
# ------------------------------------------------------------------


@mcp.tool()
def timeline_list(project: str | None = None, limit: int = 50) -> list:
    """List recent actions (newest first) for your visible projects, with
    an `reversible` flag showing which ones can be undone via timeline_undo."""
    user = _user()
    acl = _get_acl()
    visible = set(acl.visible_projects(user))
    projects = [project] if project else sorted(visible)
    projects = [p for p in projects if p in visible]
    return _get_timeline().list(projects, limit)


@mcp.tool()
def timeline_undo(action_id: str) -> dict:
    """Undo a recorded action (requires the same role the original action did)."""
    user = _user()
    acl = _get_acl()
    from .timeline.undo import undo
    return undo(_get_timeline(), acl, user, action_id)


# ------------------------------------------------------------------
# Search tools — unified retrieval with source citations (FEATURE-SEMANTIC-SEARCH.md)
# ------------------------------------------------------------------


@mcp.tool()
def search_all(query: str, projects: list[str] | None = None, limit: int = 8) -> dict:
    """Search memory notes, files and backlog items (plus your mail where
    readable) across your projects. Returns ranked results with source
    citations {project, source_type, ref, title, snippet, score} — cite the
    project/source_type/ref when you answer from these results."""
    user = _user()
    acl = _get_acl()
    cfg = config.load()
    from .search.query import search_all as _search_all
    from .tools.email import email_search as _email_search_fn
    return _search_all(
        acl, user, cfg, _get_search_store(), _get_search_embedder(),
        query, projects, limit, _email_search=_email_search_fn,
    )


@mcp.tool()
def search_reindex(project: str) -> dict:
    """Rebuild the search index for a project from its current vault content (owner only)."""
    user = _user()
    _rl(user, project)
    acl = _get_acl()
    acl.enforce(user, project, "owner")
    from .search.index import reindex_project
    return reindex_project(_get_search_store(), _get_search_embedder(), acl, project)


@mcp.tool()
def search_status() -> dict:
    """Show whether semantic search is active and how many chunks are
    indexed per project you can see."""
    user = _user()
    acl = _get_acl()
    visible = acl.visible_projects(user)
    return {
        "semantic_enabled": _get_search_embedder() is not None,
        "chunks_by_project": _get_search_store().count_by_project(visible),
    }


# ------------------------------------------------------------------
# Brief tools — proactive daily brief & notifications (FEATURE-PROACTIVE-BRIEF.md)
# ------------------------------------------------------------------

_KNOWN_CHANNEL_TYPES = {"email", "webhook", "ntfy"}


def _validate_brief_time(brief_time: str) -> None:
    import re
    if not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", brief_time or ""):
        raise ValueError(f"brief_time must be HH:MM (24h), got {brief_time!r}")


def _validate_timezone(tz_name: str) -> None:
    from zoneinfo import ZoneInfo
    try:
        ZoneInfo(tz_name)
    except Exception as exc:
        raise ValueError(f"unknown timezone: {tz_name!r}") from exc


def _validate_channels(channels: list[dict] | None) -> None:
    for spec in channels or []:
        if spec.get("type") not in _KNOWN_CHANNEL_TYPES:
            raise ValueError(
                f"unknown channel type {spec.get('type')!r}; must be one of {sorted(_KNOWN_CHANNEL_TYPES)}"
            )


@mcp.tool()
def brief_configure(
    enabled: bool,
    brief_time: str = "07:00",
    timezone: str | None = None,
    channels: list[dict] | None = None,
    quiet_hours: dict | None = None,
    projects: list[str] | None = None,
) -> dict:
    """Configure your daily brief: schedule (HH:MM in your timezone), delivery
    channels (email/webhook/ntfy), optional quiet hours, and which projects
    to cover (default: all you can see). timezone defaults to
    memaix.brief.default_timezone in config, falling back to UTC."""
    user = _user()
    cfg = config.load()
    timezone = timezone or cfg.get("memaix", {}).get("brief", {}).get("default_timezone", "UTC")
    _validate_brief_time(brief_time)
    _validate_timezone(timezone)
    _validate_channels(channels)

    from datetime import datetime, timezone as _tz
    store = _get_notify()
    prefs = store.set_prefs(
        user, now_iso=datetime.now(_tz.utc).isoformat(),
        enabled=enabled, brief_time=brief_time, timezone=timezone,
        channels=channels, projects=projects,
        quiet_start=(quiet_hours or {}).get("start"), quiet_end=(quiet_hours or {}).get("end"),
    )

    from .notify.scheduler import next_brief_epoch
    next_epoch = next_brief_epoch(prefs, datetime.now(_tz.utc))
    store.upsert_schedule(user, "daily", next_epoch)

    return {
        "ok": True, "prefs": prefs,
        "next_run": datetime.fromtimestamp(next_epoch, tz=_tz.utc).isoformat(),
    }


@mcp.tool()
def brief_status() -> dict:
    """Show your current brief configuration and next/last scheduled run."""
    user = _user()
    store = _get_notify()
    prefs = store.get_prefs(user)
    if prefs is None:
        return {"configured": False}

    from datetime import datetime, timezone as _tz
    schedule = store.get_schedule(user, "daily")
    next_run = (
        datetime.fromtimestamp(schedule["next_run"], tz=_tz.utc).isoformat() if schedule else None
    )
    last_run = (
        datetime.fromtimestamp(schedule["last_run"], tz=_tz.utc).isoformat()
        if schedule and schedule.get("last_run") else None
    )
    return {"configured": True, "prefs": prefs, "next_run": next_run, "last_run": last_run}


def _build_brief_now() -> dict:
    user = _user()
    acl = _get_acl()
    store = _get_notify()
    prefs = store.get_prefs(user) or {
        "timezone": "UTC", "brief_time": "07:00", "projects": [], "channels": [],
    }
    from datetime import datetime, timezone as _tz
    from .notify.brief import build
    return build(acl, user, config.load(), prefs, now=datetime.now(_tz.utc), tools=_brief_tools_for_user())


@mcp.tool()
def brief_preview() -> dict:
    """Build today's brief right now and return it, without sending it —
    the connector's 'fetch it when I open the app' path."""
    return _build_brief_now()


@mcp.tool()
def brief_send_now() -> dict:
    """Build and deliver your brief immediately via your configured channels.
    Ignores quiet hours and the once-per-day duplicate guard — this is an
    explicit request, so it always sends."""
    user = _user()
    acl = _get_acl()
    store = _get_notify()
    prefs = store.get_prefs(user)
    if not prefs:
        return {"ok": False, "error": "brief not configured — call brief_configure first"}

    from datetime import datetime, timezone as _tz
    from .notify.deliver import deliver
    result = deliver(
        store, acl, config.load(), user, prefs,
        now=datetime.now(_tz.utc), force=True, tools=_brief_tools_for_user(),
    )
    _get_audit().log(user, "shared", "brief_send", bool(result.get("ok")), "")
    return result


@mcp.prompt()
def daily_brief() -> str:
    """Deliver today's brief for the calling user (fetch-on-open path)."""
    return _build_brief_now()["markdown"]


# ------------------------------------------------------------------
# Automation rules & standing instructions (FEATURE-AUTOMATION-RULES.md)
# ------------------------------------------------------------------

_KNOWN_TRIGGER_TYPES = {"mail", "internal", "webhook", "schedule"}
_KNOWN_ACTION_TYPES = {"backlog_add", "memory_append", "pm_raid_add", "email_create_draft", "email_send", "notify"}
_KNOWN_CONDITION_OPS = {"contains", "equals", "matches"}
_OUTGOING_ACTION_TYPES = {"email_send", "email_create_draft"}


def _validate_rule_spec(trigger: dict, actions: list[dict], conditions: list[dict] | None) -> None:
    if not isinstance(trigger, dict) or trigger.get("type") not in _KNOWN_TRIGGER_TYPES:
        raise ValueError(f"trigger.type must be one of {sorted(_KNOWN_TRIGGER_TYPES)}")
    if not actions:
        raise ValueError("a rule needs at least one action")
    for a in actions:
        if not isinstance(a, dict) or a.get("type") not in _KNOWN_ACTION_TYPES:
            raise ValueError(f"unknown action type {a.get('type') if isinstance(a, dict) else a!r}; "
                              f"must be one of {sorted(_KNOWN_ACTION_TYPES)}")
    for c in conditions or []:
        if c.get("op") not in _KNOWN_CONDITION_OPS:
            raise ValueError(f"unknown condition op {c.get('op')!r}; must be one of {sorted(_KNOWN_CONDITION_OPS)}")


@mcp.tool()
def rule_add(
    project: str, name: str, trigger: dict, actions: list[dict], conditions: list[dict] | None = None,
) -> dict:
    """Create an automation rule: when <trigger> happens (and <conditions>
    hold), run <actions>. Requires owner if any action is outgoing
    (email_send/email_create_draft — which still goes through the outbox if
    the project is in review mode), otherwise collaborator."""
    user = _user()
    _rl(user, project)
    acl = _get_acl()
    _validate_rule_spec(trigger, actions, conditions)
    needs_owner = any(a.get("type") in _OUTGOING_ACTION_TYPES for a in actions)
    acl.enforce(user, project, "owner" if needs_owner else "collaborator")
    rule = _get_rules().add_rule(user, project, name, trigger, actions, conditions)
    return {"ok": True, "rule": rule}


@mcp.tool()
def rule_list(project: str | None = None) -> list:
    """List your automation rules for projects you can see."""
    user = _user()
    acl = _get_acl()
    visible = set(acl.visible_projects(user))
    projects = [project] if project else sorted(visible)
    projects = [p for p in projects if p in visible]
    return _get_rules().list_rules(projects)


def _rule_or_404(rules, rule_id: str) -> dict:
    rule = rules.get_rule(rule_id)
    if rule is None:
        raise FileNotFoundError(f"no such rule: {rule_id!r}")
    return rule


@mcp.tool()
def rule_set_enabled(rule_id: str, enabled: bool) -> dict:
    """Enable or disable a rule (owner only)."""
    user = _user()
    acl = _get_acl()
    rules = _get_rules()
    rule = _rule_or_404(rules, rule_id)
    acl.enforce(user, rule["project"], "owner")
    return {"ok": rules.set_enabled(rule_id, enabled)}


@mcp.tool()
def rule_delete(rule_id: str) -> dict:
    """Delete a rule (owner only)."""
    user = _user()
    acl = _get_acl()
    rules = _get_rules()
    rule = _rule_or_404(rules, rule_id)
    acl.enforce(user, rule["project"], "owner")
    return {"ok": rules.delete_rule(rule_id)}


@mcp.tool()
def rule_test(rule_id: str, sample_event: dict) -> dict:
    """Dry-run a rule against a sample event — shows what it WOULD do,
    without doing it (owner only)."""
    user = _user()
    acl = _get_acl()
    rules = _get_rules()
    rule = _rule_or_404(rules, rule_id)
    acl.enforce(user, rule["project"], "owner")
    from .rules.engine import evaluate
    results = evaluate(rules, acl, sample_event, dry_run=True)
    matching = [r for r in results if r["rule_id"] == rule_id]
    return {"matched": bool(matching), "result": matching[0] if matching else None}


@mcp.tool()
def standing_set(text: str) -> dict:
    """Set your standing instructions — guidance the assistant follows every session."""
    user = _user()
    _get_rules().set_standing(user, text)
    return {"ok": True}


@mcp.tool()
def standing_get() -> dict:
    """Get your current standing instructions."""
    user = _user()
    return {"text": _get_rules().get_standing(user) or ""}


@mcp.resource("memaix://standing-instructions")
def standing_instructions_resource() -> str:
    """The calling user's standing instructions, for clients that read
    resources at session start."""
    user = _user()
    return _get_rules().get_standing(user) or ""


@mcp.tool()
def capabilities(area: str | None = None) -> dict:
    """List what Memaix can do for you right now, grouped by outcome area
    (memory, mail, calendar, backlog, pm, brief, search, automation, undo,
    outbox). Call with no area for a grouped overview; pass an area (e.g.
    'mail') to drill down into its capabilities with example prompts. Result
    is filtered to what you can actually use given your role, linked
    accounts, and project resources — locked capabilities are shown with a
    hint on how to unlock them."""
    return _capabilities_data(area)


@mcp.prompt()
def memaix_help(area: str = "") -> str:
    """Explain what Memaix can do: an overview grouped by outcome, or (given
    an area) a drill-down with example prompts and an offer to act now."""
    data = _capabilities_data(area or None)
    lines: list[str] = []
    if "areas" in data:
        lines += ["# Vad kan jag göra?", "", "Här är det jag kan hjälpa till med just nu:"]
        for entry in data["areas"]:
            titles = ", ".join(c["title"] for c in entry["capabilities"])
            lines.append(f"- **{entry['area']}**: {titles}")
        if data["locked"]:
            lines += ["", "Låst just nu:"]
            lines += [f"- {l['title']} — {l['hint']}" for l in data["locked"]]
        lines += ["", "Fråga om ett specifikt område (t.ex. \"mail\") för konkreta exempel."]
    else:
        lines += [f"# {data['area']}", ""]
        for cap in data["capabilities"]:
            lines.append(f"## {cap['title']}")
            lines.append(cap["summary"])
            examples = cap["examples"] if isinstance(cap["examples"], list) else []
            lines += [f"- \"{ex}\"" for ex in examples]
            lines.append("")
        if data["locked"]:
            lines += ["Låst just nu:"]
            lines += [f"- {l['title']} — {l['hint']}" for l in data["locked"]]
        lines += ["", "Vill du att jag gör något av detta nu?"]
    return "\n".join(lines)


@mcp.resource("memaix://capabilities")
def capabilities_resource() -> dict:
    """Same ACL/account-filtered overview as the `capabilities` tool, for
    clients that read resources at session start."""
    return _capabilities_data(None)


@mcp.tool()
def next_suggestion(last_tool: str) -> dict:
    """After calling `last_tool`, ask whether there's one natural next
    capability worth mentioning. Sparse and rate-limited — never suggests a
    locked capability, and returns {} most of the time by design."""
    from .capabilities.registry import available_for
    from .capabilities.nudges import suggest
    import time

    user = _user()
    cfg = config.load()
    t = _translator_for_config(cfg)
    available, _locked = available_for(_get_acl(), user, _get_accounts(user), cfg)
    result = suggest(user, last_tool, available, _get_nudge_state(), now=time.time())
    if result is None:
        return {}
    return {"capability_key": result["capability_key"], "title": t(result["title_key"])}


@mcp.tool()
def files_list(project: str, path: str = "/") -> list:
    """List files and directories in a project vault path."""
    return _tool_call("files_list", project, t_files.list_files, path)


@mcp.tool()
def files_read(project: str, path: str) -> str:
    """Read a file from a project vault."""
    return _tool_call("files_read", project, t_files.read_file, path)


@mcp.tool()
def files_write(project: str, path: str, content: str) -> str:
    """Write a file to a project vault."""
    return _tool_call("files_write", project, t_files.write_file, path, content)


@mcp.tool()
def files_search(project: str, query: str, path: str = "/") -> list:
    """Search file contents in a project vault."""
    return _tool_call("files_search", project, t_files.search_files, query, path)


# ------------------------------------------------------------------
# Memory tools
# ------------------------------------------------------------------


@mcp.tool()
def memory_read(project: str, note: str) -> dict:
    """Read a memory note from a project vault."""
    return _tool_call("memory_read", project, t_memory.memory_read, note)


@mcp.tool()
def memory_search(project: str, query: str) -> list:
    """Full-text search across memory notes in a project vault."""
    return _tool_call("memory_search", project, t_memory.memory_search, query)


@mcp.tool()
def memory_write(project: str, note: str, content: str) -> dict:
    """Write (overwrite) a memory note."""
    return _tool_call("memory_write", project, t_memory.memory_write, note, content)


@mcp.tool()
def memory_append(project: str, note: str, text: str) -> dict:
    """Append text to a memory note (creates if absent)."""
    return _tool_call("memory_append", project, t_memory.memory_append, note, text)


@mcp.tool()
def memory_history(project: str, note: str | None = None, limit: int = 20) -> list:
    """Git log for a note or the whole vault."""
    return _tool_call("memory_history", project, t_memory.memory_history, note, limit)


@mcp.tool()
def memory_revert(project: str, commit: str) -> dict:
    """Revert a git commit in the project vault."""
    return _tool_call("memory_revert", project, t_memory.memory_revert, commit)


# ------------------------------------------------------------------
# Backlog tools
# ------------------------------------------------------------------


@mcp.tool()
def backlog_add(project: str, title: str, description: str, category: str | None = None) -> dict:
    """Create a new backlog item (status: inbox)."""
    return _tool_call("backlog_add", project, t_backlog.backlog_add, title, description, category)


@mcp.tool()
def backlog_list(project: str, status: str | None = None, category: str | None = None) -> list:
    """List backlog items, optionally filtered by status or category."""
    return _tool_call("backlog_list", project, t_backlog.backlog_list, status, category)


@mcp.tool()
def backlog_get(project: str, id: str) -> dict:
    """Fetch a single backlog item by id."""
    return _tool_call("backlog_get", project, t_backlog.backlog_get, id)


@mcp.tool()
def backlog_score(
    project: str,
    id: str,
    expected_version: int,
    value: int | None = None,
    complexity: int | None = None,
    risk: int | None = None,
) -> dict:
    """Update scoring fields on a backlog item (optimistic locking)."""
    return _tool_call(
        "backlog_score", project, t_backlog.backlog_score,
        id, expected_version, value, complexity, risk,
    )


@mcp.tool()
def backlog_comment(project: str, id: str, text: str, expected_version: int) -> dict:
    """Append a comment to a backlog item (optimistic locking)."""
    return _tool_call(
        "backlog_comment", project, t_backlog.backlog_comment,
        id, text, expected_version,
    )


@mcp.tool()
def backlog_set_status(project: str, id: str, status: str, expected_version: int) -> dict:
    """Transition a backlog item to a new status (owner only, optimistic locking)."""
    return _tool_call(
        "backlog_set_status", project, t_backlog.backlog_set_status,
        id, status, expected_version,
    )


# ------------------------------------------------------------------
# PM tools
# ------------------------------------------------------------------


@mcp.tool()
def pm_set_methodology(
    project: str,
    methodology: str,
    sprint_length_days: int = 14,
    capacity: dict | None = None,
) -> dict:
    """Set project methodology and sprint capacity (owner only)."""
    return _tool_call(
        "pm_set_methodology", project, t_pm.pm_set_methodology,
        methodology, sprint_length_days, capacity,
    )


@mcp.tool()
def pm_status_report(project: str, note: str = "status") -> dict:
    """Generate a status report snapshot from backlog, RAID and memory notes."""
    return _tool_call("pm_status_report", project, t_pm.pm_status_report, note)


@mcp.tool()
def pm_plan_sprint(
    project: str,
    sprint_id: str,
    item_ids: list[str],
    goal: str = "",
) -> dict:
    """Commit backlog items into a named sprint and stamp each item (owner only)."""
    return _tool_call(
        "pm_plan_sprint", project, t_pm.pm_plan_sprint,
        sprint_id, item_ids, goal,
    )


@mcp.tool()
def pm_sprint_status(project: str, sprint_id: str) -> dict:
    """Burndown summary for a sprint: done vs remaining points."""
    return _tool_call("pm_sprint_status", project, t_pm.pm_sprint_status, sprint_id)


@mcp.tool()
def pm_raid_add(
    project: str,
    raid_type: str,
    summary: str,
    owner: str = "",
    severity: str = "medium",
    mitigation: str = "",
) -> dict:
    """Append a RAID entry (Risk/Assumption/Issue/Dependency) to the project log."""
    return _tool_call(
        "pm_raid_add", project, t_pm.pm_raid_add,
        raid_type, summary, owner, severity, mitigation,
    )


@mcp.tool()
def pm_raid_list(project: str, raid_type: str = "") -> dict:
    """List RAID entries, optionally filtered by type."""
    return _tool_call("pm_raid_list", project, t_pm.pm_raid_list, raid_type)


@mcp.prompt()
def pm_sprint_planning(project: str) -> str:
    """Guide the AI through sprint planning for a project."""
    return (
        f"You are planning a sprint for project '{project}'. "
        "1) Call backlog_list to see approved/evaluated items. "
        "2) Propose a sprint_id (e.g. SPRINT-01), a goal, and item_ids "
        "whose estimates fit the playbook capacity. "
        "3) Confirm with the user, then call pm_plan_sprint. "
        "If any item lacks an estimate, ask the user before committing."
    )


@mcp.prompt()
def pm_weekly_review(project: str) -> str:
    """Guide the AI through a weekly PM review."""
    return (
        f"Run a weekly PM review for '{project}': "
        "call pm_sprint_status on the active sprint, "
        "then pm_raid_list for open risks/issues, "
        "then pm_status_report to persist a snapshot. "
        "Summarize blockers and burndown for the user."
    )


# ------------------------------------------------------------------
# PM planning-engine tools (FEATURE-PM-ENGINE.md) — deterministic
# resource/task/critical-path/allocation engine, distinct from the
# markdown+git pm_* tools above. The engine computes; nothing here or in
# tools/pm_engine.py ever guesses a date.
# ------------------------------------------------------------------


@mcp.tool()
def resource_add(project: str, name: str, cost_per_hour: float | None = None, capacity_hours_per_day: float = 8.0) -> dict:
    """Add a plannable resource (person) to the PM engine."""
    return _tool_call(
        "resource_add", project, t_pm_engine.resource_add, name,
        cost_per_hour=cost_per_hour, capacity_hours_per_day=capacity_hours_per_day, _pm=_get_pm(),
    )


@mcp.tool()
def resource_list(project: str) -> list:
    """List PM-engine resources for a project."""
    return _tool_call("resource_list", project, t_pm_engine.resource_list, _pm=_get_pm())


@mcp.tool()
def resource_availability(
    project: str, resource_id: int, start_date: str, end_date: str, hours_per_day: float, reason: str | None = None,
) -> dict:
    """Record an availability exception (vacation, part-time, ...) for a resource."""
    return _tool_call(
        "resource_availability", project, t_pm_engine.resource_availability,
        resource_id, start_date, end_date, hours_per_day, reason, _pm=_get_pm(),
    )


@mcp.tool()
def resource_set_skill(project: str, resource_id: int, skill: str, level: int | None = None) -> dict:
    """Tag a resource with a skill (creates the skill if it's new)."""
    return _tool_call(
        "resource_set_skill", project, t_pm_engine.resource_set_skill, resource_id, skill, level, _pm=_get_pm(),
    )


@mcp.tool()
def milestone_add(project: str, name: str, target_date: str | None = None) -> dict:
    """Add a milestone that tasks can be linked to."""
    return _tool_call("milestone_add", project, t_pm_engine.milestone_add, name, target_date, _pm=_get_pm())


@mcp.tool()
def task_add(
    project: str, title: str, estimate_hours: float | None = None, required_skill: str | None = None,
    priority: int = 3, backlog_id: str | None = None, milestone_id: int | None = None,
) -> dict:
    """Add a PM-engine task (scheduled/allocated work — distinct from backlog_add)."""
    return _tool_call(
        "task_add", project, t_pm_engine.task_add, title,
        estimate_hours=estimate_hours, required_skill=required_skill, priority=priority,
        backlog_id=backlog_id, milestone_id=milestone_id, _pm=_get_pm(),
    )


@mcp.tool()
def task_estimate(project: str, task_id: int, estimate_hours: float) -> dict:
    """Set or update a task's estimate."""
    return _tool_call("task_estimate", project, t_pm_engine.task_estimate, task_id, estimate_hours, _pm=_get_pm())


@mcp.tool()
def task_log_actual(
    project: str, task_id: int, date: str, hours_logged: float | None = None,
    percent_complete: float | None = None, note: str | None = None,
) -> dict:
    """Log actual progress (hours and/or percent complete) against a task, for variance tracking."""
    return _tool_call(
        "task_log_actual", project, t_pm_engine.task_log_actual, task_id, date,
        hours_logged=hours_logged, percent_complete=percent_complete, note=note, _pm=_get_pm(),
    )


@mcp.tool()
def dependency_add(project: str, predecessor_id: int, successor_id: int, type: str = "FS", lag_days: float = 0.0) -> dict:
    """Add a task dependency (FS/SS/FF/SF). Rejected if it would create a cycle."""
    return _tool_call(
        "dependency_add", project, t_pm_engine.dependency_add,
        predecessor_id, successor_id, type, lag_days, _pm=_get_pm(),
    )


@mcp.tool()
def scenario_add(project: str, name: str) -> dict:
    """Create a planning scenario to allocate tasks against."""
    return _tool_call("scenario_add", project, t_pm_engine.scenario_add, name, _pm=_get_pm())


@mcp.tool()
def scenario_list(project: str) -> list:
    """List planning scenarios for a project."""
    return _tool_call("scenario_list", project, t_pm_engine.scenario_list, _pm=_get_pm())


@mcp.tool()
def pm_allocate(project: str, scenario_id: int, project_start: str | None = None) -> dict:
    """Run the planning engine for a scenario: critical path + resource-constrained
    allocation. Deterministic — always recomputed from resources/tasks/dependencies,
    never guessed. Owner only."""
    return _tool_call(
        "pm_allocate", project, t_pm_engine.pm_allocate, scenario_id, project_start, _pm=_get_pm(),
    )


@mcp.tool()
def pm_utilization(
    project: str, scenario_id: int, period_start: str, period_end: str, resource_id: int | None = None,
) -> dict:
    """Allocated hours vs capacity per resource over a period, for a scenario."""
    return _tool_call(
        "pm_utilization", project, t_pm_engine.pm_utilization,
        scenario_id, period_start, period_end, resource_id, _pm=_get_pm(),
    )


@mcp.tool()
def pm_variance(project: str) -> dict:
    """Compare the committed baseline plan against logged actuals (hours + schedule slippage)."""
    return _tool_call("pm_variance", project, t_pm_engine.pm_variance, _pm=_get_pm())


@mcp.tool()
def plan_commit(project: str, scenario_id: int) -> dict:
    """Freeze a scenario as the committed plan and its baseline for future variance
    tracking. Owner only; who committed it is recorded (audit)."""
    return _tool_call("plan_commit", project, t_pm_engine.plan_commit, scenario_id, _pm=_get_pm())


@mcp.tool()
def calendar_setup(
    project: str,
    mode: str,
    ical_url: str | None = None,
    calendar_id: str | None = None,
) -> dict:
    """Configure your personal calendar access mode for a project.

    mode='oauth'       — link via Google OAuth (full read+write). Returns a link_url to open.
    mode='ical_secret' — supply your Google Calendar secret iCal URL (read-only).
    mode='free_busy'   — supply your Google calendar_id (read-only, no event titles).
    mode='none'        — remove calendar configuration for this project.
    """
    user = _user()
    _rl(user, project)
    _get_acl().enforce(user, project, "collaborator")
    store = _get_token_store()
    cfg = config.load()

    if mode == "oauth":
        public_url = cfg.get("memaix", {}).get("server", {}).get("public_url", "")
        result = t_account.account_link(_get_acl(), user, "google", public_url)
        return {"ok": True, "mode": "oauth", "next": f"Öppna {result['link_url']} i din webbläsare"}

    if mode == "ical_secret":
        if not ical_url:
            return {"ok": False, "error": "ical_url krävs för mode=ical_secret"}
        # Store under synthetic provider — account key is a stable placeholder
        store.store(user, "ical_secret", "ical_secret", {"ical_url": ical_url})
        return {"ok": True, "mode": "ical_secret", "stored": True}

    if mode == "free_busy":
        if not calendar_id:
            return {"ok": False, "error": "calendar_id krävs för mode=free_busy"}
        store.store(user, "free_busy", "free_busy", {"calendar_id": calendar_id})
        return {"ok": True, "mode": "free_busy", "calendar_id": calendar_id,
                "note": "Kräver att google_api_key finns i memaix.yaml och att din kalender är publik"}

    if mode == "none":
        for provider, account in [("ical_secret", "ical_secret"), ("free_busy", "free_busy")]:
            store.delete(user, provider, account)
        return {"ok": True, "mode": "none", "note": "Kalender-koppling borttagen (OAuth-token behåller du via account_unlink)"}

    return {"ok": False, "error": f"Okänt mode: {mode!r}. Välj oauth, ical_secret, free_busy eller none"}


@mcp.tool()
def calendar_status(project: str) -> dict:
    """Show which calendar access mode is active for the calling user in this project."""
    user = _user()
    _rl(user, project)
    _get_acl().enforce(user, project, "reader")
    store = _get_token_store()
    all_accounts = store.list_accounts(user)

    google = [a for a in all_accounts if a["provider"] == "google"]
    ical = [a for a in all_accounts if a["provider"] == "ical_secret"]
    fb = [a for a in all_accounts if a["provider"] == "free_busy"]

    active = "none"
    details: dict = {}
    if google:
        active = "oauth"
        details = {"account": google[0]["account"], "status": google[0]["status"]}
    elif ical:
        active = "ical_secret"
        details = {"status": ical[0]["status"]}
    elif fb:
        active = "free_busy"
        token_data = store.load_one(user, "free_busy", "free_busy") or {}
        details = {"calendar_id": token_data.get("calendar_id", ""), "status": fb[0]["status"]}

    return {
        "active_mode": active,
        "details": details,
        "available_modes": ["oauth", "ical_secret", "free_busy"],
    }


# ------------------------------------------------------------------
# Contacts tools (FEATURE-NEXTCLOUD-BACKEND.md §5 — connector framework)
# ------------------------------------------------------------------


@mcp.tool()
def contacts_search(project: str, query: str) -> list:
    """Search the project's linked address book (e.g. Nextcloud CardDAV) by
    name, email, org, or phone substring. Returns [{id, name, email, org, phone}]."""
    from .connectors.registry import default_registry

    user = _user()
    _rl(user, project)
    acl = _get_acl()
    backend = default_registry().get(acl, _get_token_store(), project, "contacts", user)
    return _audited(
        user, project, "contacts_search", t_contacts.contacts_search, acl, user, project, query, _contacts=backend,
    )


@mcp.tool()
def contacts_get(project: str, id: str) -> dict:
    """Fetch one contact by id from the project's linked address book."""
    from .connectors.registry import default_registry

    user = _user()
    _rl(user, project)
    acl = _get_acl()
    backend = default_registry().get(acl, _get_token_store(), project, "contacts", user)
    return _audited(
        user, project, "contacts_get", t_contacts.contacts_get, acl, user, project, id, _contacts=backend,
    )


def _get_nc_files(project: str, user: str):
    from .connectors.registry import default_registry

    return default_registry().get(_get_acl(), _get_token_store(), project, "files", user)


@mcp.tool()
def nc_files_list(project: str, path: str = "/") -> list:
    """List files/directories in the project's linked Nextcloud (WebDAV) files —
    separate from files_list, which is the local vault."""
    user = _user()
    _rl(user, project)
    acl = _get_acl()
    backend = _get_nc_files(project, user)
    return _audited(user, project, "nc_files_list", t_nc_files.nc_files_list, acl, user, project, path, _files=backend)


@mcp.tool()
def nc_files_read(project: str, path: str) -> str:
    """Read a file from the project's linked Nextcloud (WebDAV) files."""
    user = _user()
    _rl(user, project)
    acl = _get_acl()
    backend = _get_nc_files(project, user)
    return _audited(user, project, "nc_files_read", t_nc_files.nc_files_read, acl, user, project, path, _files=backend)


@mcp.tool()
def nc_files_write(project: str, path: str, content: str) -> str:
    """Write a file to the project's linked Nextcloud (WebDAV) files — indexed
    for search_all like a local vault file."""
    user = _user()
    _rl(user, project)
    acl = _get_acl()
    backend = _get_nc_files(project, user)
    return _audited(
        user, project, "nc_files_write", t_nc_files.nc_files_write, acl, user, project, path, content, _files=backend,
    )


@mcp.tool()
def nc_files_search(project: str, query: str, path: str = "/") -> list:
    """Search the project's linked Nextcloud (WebDAV) files by content (skips large/binary files)."""
    user = _user()
    _rl(user, project)
    acl = _get_acl()
    backend = _get_nc_files(project, user)
    return _audited(
        user, project, "nc_files_search", t_nc_files.nc_files_search, acl, user, project, query, path, _files=backend,
    )


def _get_nc_tasks(project: str, user: str):
    from .connectors.registry import default_registry

    return default_registry().get(_get_acl(), _get_token_store(), project, "tasks", user)


@mcp.tool()
def nc_tasks_list(project: str) -> list:
    """List tasks in the project's linked Nextcloud task list (CalDAV VTODO)."""
    user = _user()
    _rl(user, project)
    acl = _get_acl()
    backend = _get_nc_tasks(project, user)
    return _audited(user, project, "nc_tasks_list", t_nc_tasks.nc_tasks_list, acl, user, project, _tasks=backend)


@mcp.tool()
def nc_tasks_add(project: str, title: str, due: str | None = None, notes: str | None = None) -> dict:
    """Add a task to the project's linked Nextcloud task list."""
    user = _user()
    _rl(user, project)
    acl = _get_acl()
    backend = _get_nc_tasks(project, user)
    return _audited(
        user, project, "nc_tasks_add", t_nc_tasks.nc_tasks_add, acl, user, project, title, due, notes, _tasks=backend,
    )


@mcp.tool()
def nc_tasks_complete(project: str, id: str) -> dict:
    """Mark a Nextcloud task complete."""
    user = _user()
    _rl(user, project)
    acl = _get_acl()
    backend = _get_nc_tasks(project, user)
    return _audited(
        user, project, "nc_tasks_complete", t_nc_tasks.nc_tasks_complete, acl, user, project, id, _tasks=backend,
    )


# ------------------------------------------------------------------
# Email tools
# ------------------------------------------------------------------


@mcp.tool()
def email_list(project: str, folder: str = "INBOX", limit: int = 20) -> list:
    """List recent messages in a mailbox folder."""
    return _tool_call("email_list", project, t_email.email_list, folder, limit)


@mcp.tool()
def email_read(project: str, id: str) -> dict:
    """Read a message by UID."""
    return _tool_call("email_read", project, t_email.email_read, id)


@mcp.tool()
def email_search(project: str, query: str, limit: int = 20) -> list:
    """Search messages by body content."""
    return _tool_call("email_search", project, t_email.email_search, query, limit)


@mcp.tool()
def email_create_draft(
    project: str,
    to: str,
    subject: str,
    body: str,
    cc: str | None = None,
    in_reply_to: str | None = None,
) -> dict:
    """Save a draft to the mailbox Drafts folder."""
    return _tool_call(
        "email_create_draft", project, t_email.email_create_draft,
        to, subject, body, cc, in_reply_to,
    )


@mcp.tool()
def email_send(project: str, to: str, subject: str, body: str, cc: str | None = None) -> dict:
    """Send an email (requires owner + allow_send feature flag)."""
    return _tool_call(
        "email_send", project, t_email.email_send,
        to, subject, body, cc,
    )


# ------------------------------------------------------------------
# Calendar tools
# ------------------------------------------------------------------


@mcp.tool()
def calendar_list(project: str, start: str, end: str) -> list | dict:
    """List calendar events within a time range (ISO 8601)."""
    user = _user()
    _rl(user, project)
    try:
        dav = _resolve_calendar_dav(project, user)
        return _audited(user, project, "calendar_list", t_cal.calendar_list, _get_acl(), user, project, start, end, _dav=dav)
    except CalendarAuthRequired as e:
        return {"auth_required": True, "link_url": e.link_url, "options": e.options, "hint": "Kör calendar_setup för att välja åtkomstläge"}


@mcp.tool()
def calendar_find_free(
    project: str, duration_min: int, within_start: str, within_end: str
) -> list | dict:
    """Find free time slots of at least duration_min minutes."""
    user = _user()
    _rl(user, project)
    try:
        dav = _resolve_calendar_dav(project, user)
        return _audited(
            user, project, "calendar_find_free",
            t_cal.calendar_find_free,
            _get_acl(), user, project, duration_min, within_start, within_end, _dav=dav,
        )
    except CalendarAuthRequired as e:
        return {"auth_required": True, "link_url": e.link_url, "options": e.options, "hint": "Kör calendar_setup för att välja åtkomstläge"}


@mcp.tool()
def calendar_create(
    project: str,
    title: str,
    start: str,
    end: str,
    attendees: list[str] | None = None,
    location: str | None = None,
    description: str | None = None,
) -> dict:
    """Create a calendar event."""
    user = _user()
    _rl(user, project)
    try:
        dav = _resolve_calendar_dav(project, user)
        return _audited(
            user, project, "calendar_create",
            t_cal.calendar_create,
            _get_acl(), user, project, title, start, end, attendees, location, description, _dav=dav,
        )
    except CalendarAuthRequired as e:
        return {"auth_required": True, "link_url": e.link_url, "options": e.options, "hint": "Kör calendar_setup för att välja åtkomstläge"}


@mcp.tool()
def calendar_update(project: str, id: str, **fields) -> dict:
    """Update fields on an existing calendar event."""
    user = _user()
    _rl(user, project)
    # Reject any leading-underscore key from the client: those names are
    # reserved for internal control kwargs (_dav/_confirmed/_outbox/_cfg) and
    # must never be settable by a caller — otherwise a client could pass
    # _confirmed=True and bypass the outbox gate in tools/calendar.py.
    fields = {k: v for k, v in fields.items() if not k.startswith("_")}
    try:
        dav = _resolve_calendar_dav(project, user)
        return _audited(
            user, project, "calendar_update",
            t_cal.calendar_update,
            _get_acl(), user, project, id, _dav=dav, **fields,
        )
    except CalendarAuthRequired as e:
        return {"auth_required": True, "link_url": e.link_url, "options": e.options, "hint": "Kör calendar_setup för att välja åtkomstläge"}


def _refresh_google_token(cfg: dict, store, user: str, account: str, token_data: dict) -> str | None:
    """Use the stored refresh_token to mint a new access_token. Updates store on success."""
    import requests as req_lib
    refresh_token = token_data.get("refresh_token")
    if not refresh_token:
        return None
    provider_cfg = cfg.get("memaix", {}).get("oauth_providers", {}).get("google", {})
    client_id = provider_cfg.get("client_id", "")
    client_secret = config.secret(provider_cfg.get("client_secret_ref", "")) or ""
    try:
        resp = req_lib.post(
            "https://oauth2.googleapis.com/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            timeout=10,
        )
        resp.raise_for_status()
        new_data = resp.json()
        # Google doesn't re-issue refresh_token on refresh — preserve the original
        new_data.setdefault("refresh_token", refresh_token)
        store.store(user, "google", account, new_data)
        return new_data.get("access_token")
    except Exception:
        return None


def _resolve_calendar_dav(project: str, user: str):
    """Return a calendar adapter for the project/user.

    Checks TokenStore for the user's configured mode in priority order:
      1. OAuth (Google Calendar REST) — provider='google'
      2. iCal secret URL — provider='ical_secret'
      3. FreeBusy (read-only) — provider='free_busy'
      None → fall back to static CalDAV config from acl.yaml.
    Raises CalendarAuthRequired if project requires per_user but nothing is configured.
    """
    acl = _get_acl()
    cal_cfg = acl.resource(project, "calendar")
    cfg = config.load()
    store = _get_token_store()
    require_per_user = isinstance(cal_cfg, dict) and cal_cfg.get("auth") == "per_user"
    public_url = cfg.get("memaix", {}).get("server", {}).get("public_url", "")
    all_accounts = store.list_accounts(user)

    # 1. OAuth (Google)
    google_accounts = [a for a in all_accounts if a["provider"] == "google"]
    if google_accounts:
        account_email = google_accounts[0]["account"]
        token_data = store.load_one(user, "google", account_email)
        if token_data:
            import time
            access_token = token_data.get("access_token")
            expires_at = token_data.get("expires_at") or (
                token_data.get("created_at", 0) + token_data.get("expires_in", 3600)
            )
            if not access_token or (
                isinstance(expires_at, (int, float)) and expires_at - 60 < time.time()
            ):
                access_token = _refresh_google_token(cfg, store, user, account_email, token_data)
                if not access_token:
                    store.mark_needs_relink(user, "google", account_email)
            if access_token:
                return _PerUserGoogleAdapter(access_token)

    # 2. iCal secret URL
    ical_accounts = [a for a in all_accounts if a["provider"] == "ical_secret"]
    if ical_accounts:
        token_data = store.load_one(user, "ical_secret", ical_accounts[0]["account"])
        if token_data and token_data.get("ical_url"):
            return _ICalAdapter(token_data["ical_url"])

    # 3. FreeBusy
    fb_accounts = [a for a in all_accounts if a["provider"] == "free_busy"]
    if fb_accounts:
        token_data = store.load_one(user, "free_busy", fb_accounts[0]["account"])
        api_key = cfg.get("memaix", {}).get("google_api_key", "")
        if token_data and token_data.get("calendar_id") and api_key:
            return _FreeBusyAdapter(token_data["calendar_id"], api_key)

    if not require_per_user:
        return None  # use static CalDAV from acl.yaml

    # Nothing configured — raise with all three setup options
    oauth_link = ""
    if public_url:
        try:
            oauth_link = t_account.account_link(acl, user, "google", public_url)["link_url"]
        except Exception:
            pass
    raise CalendarAuthRequired(
        link_url=oauth_link,
        options=[
            {
                "mode": "oauth",
                "label": "Google Calendar (full access, read+write)",
                "action": f"Öppna {oauth_link} och logga in med Google",
            },
            {
                "mode": "ical_secret",
                "label": "iCal secret URL (read-only, alla providers)",
                "action": "calendar_setup(mode='ical_secret', ical_url='din-hemliga-ical-url')",
            },
            {
                "mode": "free_busy",
                "label": "FreeBusy (visar bara ledig/upptagen, kräver publik kalender)",
                "action": "calendar_setup(mode='free_busy', calendar_id='din@gmail.com')",
            },
        ],
    )


def build_http_app():
    """Build the Starlette app with Bearer-auth for HTTP transport."""
    from starlette.routing import Route
    from starlette.responses import JSONResponse, RedirectResponse
    from starlette.requests import Request
    from starlette.middleware.cors import CORSMiddleware

    # ------------------------------------------------------------------
    # Custom HTTP handlers
    # ------------------------------------------------------------------

    async def health_handler(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "service": "memaix"})

    async def protected_resource_handler(request: Request) -> JSONResponse:
        """RFC 9728 protected resource metadata.

        FastMCP auto-generates this from AuthSettings.resource_server_url, but
        Pydantic's AnyHttpUrl always adds a trailing slash.  That creates a
        mismatch when claude.ai validates the JWT aud claim against the
        connector URL (typically typed without a trailing slash).  We override
        it here so the resource value is canonical without a trailing slash,
        which matches both forms.
        """
        cfg = config.load()
        auth_cfg = cfg.get("memaix", {}).get("auth", {})
        issuer = auth_cfg.get("issuer", "https://mcp.example.com/").rstrip("/")
        resource = auth_cfg.get("resource_server_url", issuer + "/").rstrip("/")
        return JSONResponse(
            {
                "resource": resource,
                "authorization_servers": [issuer + "/"],
                "bearer_methods_supported": ["header"],
            },
            headers={"Cache-Control": "public, max-age=3600"},
        )

    async def as_metadata_handler(request: Request) -> JSONResponse:
        """Serve OAuth AS metadata with registration_endpoint injected.

        Hydra v2 doesn't advertise registration_endpoint in its discovery
        document even when DCR is enabled — this handler proxies Hydra's
        openid-configuration and adds the missing field.
        """
        import httpx
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "http://hydra:4444/.well-known/openid-configuration",
                    timeout=5.0,
                )
                metadata = resp.json()
        except Exception:
            # Fallback: return minimal metadata so discovery doesn't hard-fail
            cfg = config.load()
            issuer = cfg.get("memaix", {}).get("auth", {}).get("issuer", "https://mcp.example.com")
            metadata = {"issuer": issuer}

        issuer = metadata.get("issuer", "https://mcp.example.com").rstrip("/")
        metadata["registration_endpoint"] = f"{issuer}/oauth2/register"
        return JSONResponse(metadata)

    async def dcr_handler(request: Request) -> JSONResponse:
        """Proxy DCR to Hydra, injecting resource audience so JWTs include aud claim.

        Hydra issues JWTs without aud unless the client's audience list explicitly
        contains the resource URL. This handler ensures every dynamically registered
        client is whitelisted for https://mcp.example.com (with and without trailing
        slash) before forwarding to Hydra's public DCR endpoint.
        """
        import httpx
        try:
            body = await request.json()
        except Exception:
            body = {}

        cfg = config.load()
        issuer = cfg.get("memaix", {}).get("auth", {}).get("issuer", "https://mcp.example.com").rstrip("/")
        resource_urls = [f"{issuer}/", issuer]
        existing = body.get("audience") or []
        body["audience"] = list({*existing, *resource_urls})

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "http://hydra:4444/oauth2/register",
                    json=body,
                    headers={"Content-Type": "application/json"},
                    timeout=10.0,
                )
                return JSONResponse(resp.json(), status_code=resp.status_code)
        except Exception as exc:
            logger.warning("DCR proxy error: %s", exc)
            return JSONResponse({"error": "server_error"}, status_code=500)

    async def link_start(request: Request) -> "RedirectResponse | JSONResponse":
        """Start OAuth flow for a provider."""
        provider = request.path_params["provider"]
        state = request.query_params.get("state", "")

        PROVIDER_AUTH_URLS = {
            "google": "https://accounts.google.com/o/oauth2/v2/auth",
            "microsoft": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        }
        if provider not in PROVIDER_AUTH_URLS:
            return JSONResponse({"error": "unknown_provider"}, status_code=400)

        cfg = config.load()
        provider_cfg = cfg.get("memaix", {}).get("oauth_providers", {}).get(provider, {})
        client_id = provider_cfg.get("client_id", "")
        public_url = cfg.get("memaix", {}).get("server", {}).get("public_url", "http://localhost:8080")
        redirect_uri = f"{public_url.rstrip('/')}/link/{provider}/callback"

        from urllib.parse import urlencode
        params = {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "state": state,
            "scope": " ".join(provider_cfg.get("scopes", [])),
            "access_type": "offline",
            "prompt": "consent",
        }
        auth_url = PROVIDER_AUTH_URLS[provider] + "?" + urlencode(params)
        return RedirectResponse(auth_url)

    async def link_callback(request: Request) -> JSONResponse:
        """Handle OAuth callback: exchange code for tokens and store them."""
        provider = request.path_params["provider"]
        code = request.query_params.get("code", "")
        state = request.query_params.get("state", "")
        error = request.query_params.get("error", "")

        if error:
            return JSONResponse({"error": error}, status_code=400)

        from .tools.account import validate_state
        pending = validate_state(state)
        if not pending:
            return JSONResponse({"error": "invalid_or_expired_state"}, status_code=400)

        user_id = pending["user_id"]
        cfg = config.load()
        provider_cfg = cfg.get("memaix", {}).get("oauth_providers", {}).get(provider, {})
        public_url = cfg.get("memaix", {}).get("server", {}).get("public_url", "http://localhost:8080")
        redirect_uri = f"{public_url.rstrip('/')}/link/{provider}/callback"

        PROVIDER_TOKEN_URLS = {
            "google": "https://oauth2.googleapis.com/token",
            "microsoft": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        }
        token_url = PROVIDER_TOKEN_URLS.get(provider, "")
        client_secret = config.secret(provider_cfg.get("client_secret_ref", "")) or ""

        import requests as req_lib
        try:
            resp = req_lib.post(
                token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": provider_cfg.get("client_id", ""),
                    "client_secret": client_secret,
                },
                timeout=10,
            )
            resp.raise_for_status()
            token_data = resp.json()
        except Exception as exc:
            return JSONResponse(
                {"error": "token_exchange_failed", "detail": str(exc)}, status_code=500
            )

        account_email = token_data.get("email", "") or _get_account_email(provider, token_data)

        store = _get_token_store()
        store.store(user_id, provider, account_email, token_data)

        provider_label = {"google": "Google", "microsoft": "Microsoft"}.get(provider, provider.title())
        board_url = public_url.rstrip("/") + "/board"
        html = f"""<!doctype html>
<html lang="sv">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Konto kopplat — Memaix</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #0f1117; color: #e2e8f0;
      min-height: 100vh; display: flex; align-items: center; justify-content: center;
    }}
    .card {{
      background: #1a1f2e; border: 1px solid #2d3748; border-radius: 12px;
      padding: 2.5rem 3rem; max-width: 420px; width: 90%; text-align: center;
    }}
    .icon {{
      width: 56px; height: 56px; border-radius: 50%;
      background: #1a3a2a; border: 2px solid #38a169;
      display: flex; align-items: center; justify-content: center;
      margin: 0 auto 1.5rem;
      font-size: 1.6rem;
    }}
    h1 {{ font-size: 1.25rem; font-weight: 600; margin-bottom: .5rem; color: #f7fafc; }}
    .provider {{ color: #68d391; font-weight: 600; }}
    .account {{
      margin: 1.25rem auto 0;
      background: #0f1117; border: 1px solid #2d3748; border-radius: 8px;
      padding: .6rem 1rem; font-size: .85rem; color: #a0aec0;
      word-break: break-all;
    }}
    .account span {{ color: #e2e8f0; }}
    .actions {{ margin-top: 2rem; display: flex; gap: .75rem; justify-content: center; flex-wrap: wrap; }}
    a.btn {{
      display: inline-block; padding: .55rem 1.25rem; border-radius: 8px;
      font-size: .875rem; font-weight: 500; text-decoration: none; cursor: pointer;
    }}
    a.btn-primary {{ background: #2b6cb0; color: #fff; }}
    a.btn-primary:hover {{ background: #2c5282; }}
    a.btn-ghost {{ border: 1px solid #2d3748; color: #a0aec0; }}
    a.btn-ghost:hover {{ background: #2d3748; color: #e2e8f0; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">✓</div>
    <h1><span class="provider">{provider_label}</span> kopplat</h1>
    <p style="color:#a0aec0;font-size:.9rem;margin-top:.4rem">Ditt konto är länkat och redo att användas.</p>
    <div class="account">Inloggad som <span>{account_email or "okänt konto"}</span></div>
    <div class="actions">
      <a class="btn btn-primary" href="{board_url}">Tillbaka till board</a>
      <a class="btn btn-ghost" href="javascript:window.close()">Stäng fliken</a>
    </div>
  </div>
</body>
</html>"""
        from starlette.responses import HTMLResponse as _HTMLResponse
        return _HTMLResponse(html)

    async def rule_webhook(request: Request) -> JSONResponse:
        """Inbound trigger for webhook-type automation rules (FEATURE-AUTOMATION-RULES.md §6).

        The token is itself the shared secret (a random 'token' generated when
        the rule was created) — simplified from the design doc's HMAC-signature
        proposal since a sufficiently random URL segment is a standard, simpler
        webhook-auth pattern (e.g. Slack incoming webhooks). Rate-limited like
        any other externally reachable endpoint would need to be in production.
        """
        token = request.path_params["token"]
        try:
            body = await request.json()
        except Exception:
            body = {}

        import hashlib
        import json as _json
        digest = hashlib.sha256(_json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()[:16]
        event = {
            "type": "webhook", "project": None, "id": f"webhook:{token}:{digest}",
            "payload": {**body, "token": token},
        }
        from .rules.engine import evaluate
        results = evaluate(_get_rules(), _get_acl(), event)
        if not results:
            return JSONResponse({"error": "no matching enabled rule for this token"}, status_code=404)
        return JSONResponse({"ok": True, "matched": len(results)})

    # ------------------------------------------------------------------

    cfg = config.load()
    auth_cfg = cfg.get("memaix", {}).get("auth", {})

    if auth_cfg.get("issuer"):
        from .auth.token import HydraTokenVerifier
        from mcp.server.auth.settings import AuthSettings
        verifier = HydraTokenVerifier.from_config(cfg)
        mcp.settings.auth = AuthSettings(
            issuer_url=auth_cfg["issuer"],
            resource_server_url=auth_cfg.get("resource_server_url", auth_cfg["issuer"]),
        )
        mcp._token_verifier = verifier

    # FastMCP's DNS rebinding protection defaults to allowed_hosts=[] when binding
    # to 0.0.0.0 (as opposed to localhost), which causes 421 for every real hostname.
    # Explicitly allow the public host extracted from resource_server_url.
    from mcp.server.transport_security import TransportSecuritySettings
    from urllib.parse import urlparse as _urlparse2
    _pub_host = _urlparse2(
        auth_cfg.get("resource_server_url", auth_cfg.get("issuer", ""))
    ).netloc or "mcp.example.com"
    mcp.settings.transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[_pub_host],
    )

    # Mount at root so claude.ai finds the endpoint at the connector URL directly.
    mcp.settings.streamable_http_path = "/"

    from .board.routes import board_routes

    custom_routes = [
        Route("/health", health_handler),
        Route("/.well-known/oauth-authorization-server", as_metadata_handler),
        Route("/oauth2/register", dcr_handler, methods=["POST"]),
        Route("/link/{provider}", link_start),
        Route("/link/{provider}/callback", link_callback),
        Route("/hooks/{token}", rule_webhook, methods=["POST"]),
        *board_routes,
    ]

    mcp._custom_starlette_routes = custom_routes
    starlette_app = mcp.streamable_http_app()

    # FastMCP appends custom_starlette_routes AFTER its built-in routes, so the
    # auto-generated /.well-known/oauth-protected-resource route wins.  Prepend
    # our handler into the Starlette router routes list so it matches first.
    from starlette.routing import Route as _Route
    starlette_app.router.routes.insert(
        0, _Route("/.well-known/oauth-protected-resource", protected_resource_handler)
    )

    # Start the proactive-brief scheduler (FEATURE-PROACTIVE-BRIEF.md §7).
    # Runs as a background asyncio task inside the same process as the HTTP
    # server; a single worker deployment is assumed (see docs's multi-worker
    # note — the schedule table's compare-and-set claim keeps a second worker
    # from double-sending, but only one worker needs to run the loop at all).
    # Starlette dropped add_event_handler(); wrap the router's lifespan context
    # manager instead so our task starts/stops alongside FastMCP's own lifespan.
    if cfg.get("memaix", {}).get("brief", {}).get("enabled", True):
        import contextlib

        _original_lifespan = starlette_app.router.lifespan_context

        @contextlib.asynccontextmanager
        async def _lifespan_with_scheduler(app):
            import asyncio
            from .notify.deliver import deliver as _deliver_brief
            from .notify.scheduler import scheduler_loop

            def _deliver_for_user(user, prefs, now):
                _deliver_brief(
                    _get_notify(), _get_acl(), config.load(), user, prefs,
                    now=now, tools=_brief_tools_for_user(),
                )

            task = asyncio.create_task(scheduler_loop(_get_notify(), _deliver_for_user))
            try:
                async with _original_lifespan(app) as state:
                    yield state
            finally:
                task.cancel()

        starlette_app.router.lifespan_context = _lifespan_with_scheduler

    # Wrap with CORS so claude.ai browser requests aren't blocked.
    app = CORSMiddleware(
        app=starlette_app,
        allow_origins=["https://claude.ai", "https://api.claude.ai"],
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "mcp-session-id"],
        expose_headers=["mcp-session-id"],
    )

    return app


def _decode_id_token_claims(id_token: str) -> dict:
    """Decode an OIDC id_token's claims without verifying the signature.

    Safe here: the token was obtained directly from the provider's token
    endpoint over TLS during the exchange above (never supplied by the
    client), and is only used to derive a stable account identifier — not to
    authenticate a request. Returns {} on any decode failure.
    """
    import jwt
    try:
        return jwt.decode(
            id_token,
            options={"verify_signature": False, "verify_aud": False, "verify_exp": False},
        )
    except Exception:
        return {}


def _get_account_email(provider: str, token_data: dict) -> str:
    """Derive a stable per-account identifier from the token response.

    Google/Microsoft never put the email in the token endpoint body itself —
    it lives in the id_token's claims (requires an 'openid'+'email' scope).
    Without this, every linked account for a provider fell back to the same
    'linked-<provider>' key and a second linked account silently overwrote
    the first in the token store. Falls back to the token's 'sub' (still
    unique per account) before the last-resort shared placeholder.
    """
    id_token = token_data.get("id_token")
    if id_token:
        claims = _decode_id_token_claims(id_token)
        email = claims.get("email") or claims.get("preferred_username") or claims.get("upn")
        if email:
            return email
        sub = claims.get("sub")
        if sub:
            return f"{provider}-{sub}"
    return f"linked-{provider}"


def main() -> None:
    import sys
    if "--http" in sys.argv or os.environ.get("MEMAIX_TRANSPORT") == "http":
        import uvicorn
        app = build_http_app()
        cfg = config.load()
        bind = cfg.get("memaix", {}).get("server", {}).get("bind", "0.0.0.0:8080")
        host, port = bind.rsplit(":", 1)
        uvicorn.run(app, host=host, port=int(port), log_level="info")
    else:
        mcp.run()


if __name__ == "__main__":
    main()
