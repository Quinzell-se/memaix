# SPDX-License-Identifier: AGPL-3.0-or-later
"""MCP server entrypoint — Fas 3: HTTP transport + Hydra token auth.

User identity:
  HTTP mode  — Bearer JWT verified by HydraTokenVerifier, subject mapped via acl.yaml.
  stdio mode — MEMAIX_USER env var (backward-compatible).
Rate limiting: 60 req/min per user, 120 req/min per project.
Audit: every tool call is logged to the audit DB (MEMAIX_AUDIT_DB or /tmp/...).
"""

from __future__ import annotations

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from . import config
from .acl import Acl
from .safety.audit import AuditLog
from .safety.rate_limit import rate_limiter as _rate_limiter
from .tools import files as t_files
from .tools import whoami as t_whoami
from .tools import memory as t_memory
from .tools import backlog as t_backlog
from .tools import email as t_email
from .tools import calendar as t_cal
from .tools import account as t_account

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
            # Development fallback — warn and generate a temporary key.
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


mcp = FastMCP("memaix")


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
    user = _user()
    _rl(user, project)
    return _audited(user, project, "files_list", t_files.list_files, _get_acl(), user, project, path)


@mcp.tool()
def files_read(project: str, path: str) -> str:
    """Read a file from a project vault."""
    user = _user()
    _rl(user, project)
    return _audited(user, project, "files_read", t_files.read_file, _get_acl(), user, project, path)


@mcp.tool()
def files_write(project: str, path: str, content: str) -> str:
    """Write a file to a project vault."""
    user = _user()
    _rl(user, project)
    return _audited(user, project, "files_write", t_files.write_file, _get_acl(), user, project, path, content)


@mcp.tool()
def files_search(project: str, query: str, path: str = "/") -> list:
    """Search file contents in a project vault."""
    user = _user()
    _rl(user, project)
    return _audited(user, project, "files_search", t_files.search_files, _get_acl(), user, project, query, path)


# ------------------------------------------------------------------
# Memory tools
# ------------------------------------------------------------------


@mcp.tool()
def memory_read(project: str, note: str) -> dict:
    """Read a memory note from a project vault."""
    user = _user()
    _rl(user, project)
    return _audited(user, project, "memory_read", t_memory.memory_read, _get_acl(), user, project, note)


@mcp.tool()
def memory_search(project: str, query: str) -> list:
    """Full-text search across memory notes in a project vault."""
    user = _user()
    _rl(user, project)
    return _audited(user, project, "memory_search", t_memory.memory_search, _get_acl(), user, project, query)


@mcp.tool()
def memory_write(project: str, note: str, content: str) -> dict:
    """Write (overwrite) a memory note."""
    user = _user()
    _rl(user, project)
    return _audited(user, project, "memory_write", t_memory.memory_write, _get_acl(), user, project, note, content)


@mcp.tool()
def memory_append(project: str, note: str, text: str) -> dict:
    """Append text to a memory note (creates if absent)."""
    user = _user()
    _rl(user, project)
    return _audited(user, project, "memory_append", t_memory.memory_append, _get_acl(), user, project, note, text)


@mcp.tool()
def memory_history(project: str, note: str | None = None, limit: int = 20) -> list:
    """Git log for a note or the whole vault."""
    user = _user()
    _rl(user, project)
    return _audited(user, project, "memory_history", t_memory.memory_history, _get_acl(), user, project, note, limit)


@mcp.tool()
def memory_revert(project: str, commit: str) -> dict:
    """Revert a git commit in the project vault."""
    user = _user()
    _rl(user, project)
    return _audited(user, project, "memory_revert", t_memory.memory_revert, _get_acl(), user, project, commit)


# ------------------------------------------------------------------
# Backlog tools
# ------------------------------------------------------------------


@mcp.tool()
def backlog_add(project: str, title: str, description: str, category: str | None = None) -> dict:
    """Create a new backlog item (status: inbox)."""
    user = _user()
    _rl(user, project)
    return _audited(user, project, "backlog_add", t_backlog.backlog_add, _get_acl(), user, project, title, description, category)


@mcp.tool()
def backlog_list(project: str, status: str | None = None, category: str | None = None) -> list:
    """List backlog items, optionally filtered by status or category."""
    user = _user()
    _rl(user, project)
    return _audited(user, project, "backlog_list", t_backlog.backlog_list, _get_acl(), user, project, status, category)


@mcp.tool()
def backlog_get(project: str, id: str) -> dict:
    """Fetch a single backlog item by id."""
    user = _user()
    _rl(user, project)
    return _audited(user, project, "backlog_get", t_backlog.backlog_get, _get_acl(), user, project, id)


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
    user = _user()
    _rl(user, project)
    return _audited(
        user, project, "backlog_score",
        t_backlog.backlog_score,
        _get_acl(), user, project, id, expected_version, value, complexity, risk,
    )


@mcp.tool()
def backlog_comment(project: str, id: str, text: str, expected_version: int) -> dict:
    """Append a comment to a backlog item (optimistic locking)."""
    user = _user()
    _rl(user, project)
    return _audited(
        user, project, "backlog_comment",
        t_backlog.backlog_comment,
        _get_acl(), user, project, id, text, expected_version,
    )


@mcp.tool()
def backlog_set_status(project: str, id: str, status: str, expected_version: int) -> dict:
    """Transition a backlog item to a new status (owner only, optimistic locking)."""
    user = _user()
    _rl(user, project)
    return _audited(
        user, project, "backlog_set_status",
        t_backlog.backlog_set_status,
        _get_acl(), user, project, id, status, expected_version,
    )


# ------------------------------------------------------------------
# Email tools
# ------------------------------------------------------------------


@mcp.tool()
def email_list(project: str, folder: str = "INBOX", limit: int = 20) -> list:
    """List recent messages in a mailbox folder."""
    user = _user()
    _rl(user, project)
    return _audited(user, project, "email_list", t_email.email_list, _get_acl(), user, project, folder, limit)


@mcp.tool()
def email_read(project: str, id: str) -> dict:
    """Read a message by UID."""
    user = _user()
    _rl(user, project)
    return _audited(user, project, "email_read", t_email.email_read, _get_acl(), user, project, id)


@mcp.tool()
def email_search(project: str, query: str, limit: int = 20) -> list:
    """Search messages by body content."""
    user = _user()
    _rl(user, project)
    return _audited(user, project, "email_search", t_email.email_search, _get_acl(), user, project, query, limit)


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
    user = _user()
    _rl(user, project)
    return _audited(
        user, project, "email_create_draft",
        t_email.email_create_draft,
        _get_acl(), user, project, to, subject, body, cc, in_reply_to,
    )


@mcp.tool()
def email_send(project: str, to: str, subject: str, body: str, cc: str | None = None) -> dict:
    """Send an email (requires owner + allow_send feature flag)."""
    user = _user()
    _rl(user, project)
    return _audited(
        user, project, "email_send",
        t_email.email_send,
        _get_acl(), user, project, to, subject, body, cc,
    )


# ------------------------------------------------------------------
# Calendar tools
# ------------------------------------------------------------------


@mcp.tool()
def calendar_list(project: str, start: str, end: str) -> list:
    """List calendar events within a time range (ISO 8601)."""
    user = _user()
    _rl(user, project)
    return _audited(user, project, "calendar_list", t_cal.calendar_list, _get_acl(), user, project, start, end)


@mcp.tool()
def calendar_find_free(
    project: str, duration_min: int, within_start: str, within_end: str
) -> list:
    """Find free time slots of at least duration_min minutes."""
    user = _user()
    _rl(user, project)
    return _audited(
        user, project, "calendar_find_free",
        t_cal.calendar_find_free,
        _get_acl(), user, project, duration_min, within_start, within_end,
    )


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
    return _audited(
        user, project, "calendar_create",
        t_cal.calendar_create,
        _get_acl(), user, project, title, start, end, attendees, location, description,
    )


@mcp.tool()
def calendar_update(project: str, id: str, **fields) -> dict:
    """Update fields on an existing calendar event."""
    user = _user()
    _rl(user, project)
    return _audited(
        user, project, "calendar_update",
        t_cal.calendar_update,
        _get_acl(), user, project, id, **fields,
    )


@mcp.tool()
def calendar_delete(project: str, id: str) -> dict:
    """Delete a calendar event (always returns requires_confirmation=True)."""
    user = _user()
    _rl(user, project)
    return _audited(
        user, project, "calendar_delete",
        t_cal.calendar_delete,
        _get_acl(), user, project, id,
    )


def build_http_app():
    """Build the Starlette app with Bearer-auth for HTTP transport."""
    from starlette.routing import Route
    from starlette.responses import JSONResponse, RedirectResponse
    from starlette.requests import Request

    # ------------------------------------------------------------------
    # Custom HTTP handlers
    # ------------------------------------------------------------------

    async def health_handler(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "service": "memaix"})

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

        return JSONResponse(
            {"status": "linked", "provider": provider, "account": account_email}
        )

    # ------------------------------------------------------------------

    cfg = config.load()
    auth_cfg = cfg.get("memaix", {}).get("auth", {})

    if auth_cfg.get("issuer"):
        from .auth.token import HydraTokenVerifier
        verifier = HydraTokenVerifier.from_config(cfg)
        try:
            from mcp.server.fastmcp.settings import AuthSettings
            mcp.settings.auth = AuthSettings(
                issuer_url=auth_cfg["issuer"],
                resource_server_url=auth_cfg.get("resource_server_url", auth_cfg["issuer"]),
            )
        except (ImportError, AttributeError):
            pass
        try:
            mcp._token_verifier = verifier
        except AttributeError:
            pass

    custom_routes = [
        Route("/health", health_handler),
        Route("/link/{provider}", link_start),
        Route("/link/{provider}/callback", link_callback),
    ]

    try:
        mcp._custom_starlette_routes = custom_routes
        app = mcp.streamable_http_app()
    except AttributeError:
        app = mcp.streamable_http_app()
        try:
            for route in reversed(custom_routes):
                app.routes.insert(0, route)
        except AttributeError:
            pass

    return app


def _get_account_email(provider: str, token_data: dict) -> str:
    """Extract account email from token response or return a placeholder."""
    return token_data.get("email", f"linked-{provider}")


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
