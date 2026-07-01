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
from .acl import Acl
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
from .tools import onboarding as t_onboarding
from .tools import pm as t_pm
from .tools.calendar import CalendarAuthRequired, _PerUserGoogleAdapter, _ICalAdapter, _FreeBusyAdapter

logger = logging.getLogger(__name__)

_acl: Acl | None = None
_audit: AuditLog | None = None
_token_store: "TokenStore | None" = None  # type: ignore[name-defined]


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
    """Call fn(*args, **kwargs), log result to audit, re-raise on error."""
    try:
        result = fn(*args, **kwargs)
        _get_audit().log(user, project, tool, True)
        return result
    except Exception as exc:
        _get_audit().log(user, project, tool, False, str(exc))
        raise


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
    return _audited(
        user, "shared", "onboarding_complete",
        t_onboarding.complete_onboarding, user, Path(shared_vault), profile_content,
    )


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
