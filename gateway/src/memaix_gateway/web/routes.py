# SPDX-License-Identifier: AGPL-3.0-or-later
"""Web-UI app-shell routes — /app pages, static assets and /app/api/me.

Auth reuses the board's signed cookie (board/routes.py::_check_cookie): the
/app pages and /board share one stateless HMAC session — no SessionMiddleware,
no server-side session store (FEATURE-WEB-UI-FOUNDATION.md §2.6).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from starlette.requests import Request
from starlette.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
from starlette.routing import Route

from ..board.routes import _board_html_with_locale, _check_cookie, _config_locale
from ..i18n import locale_from_request

_WEB_DIR = Path(__file__).parent
_PAGES = _WEB_DIR / "pages"
_STATIC = _WEB_DIR / "static"
_HTML_CACHE: dict[str, str] = {}

# Pages the generic /app/{page} route may serve. An allowlist (rather than
# "whatever exists on disk") keeps the URL space intentional.
_KNOWN_PAGES = {"home", "board", "settings", "memory", "outbox", "admin", "search"}

_STATIC_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
}


def _get_acl():
    # Lazy indirection to server's cached Acl so reload_acl() takes effect here
    # too (FEATURE-WEB-UI-FOUNDATION.md reconciliation note). Function-level
    # import avoids a module-import cycle with server.py.
    from ..server import _get_acl as _srv_get_acl

    return _srv_get_acl()


def _require_user(request: Request) -> str | None:
    """Authenticated user from the signed board cookie, or None."""
    return _check_cookie(request)


def _json_401() -> JSONResponse:
    return JSONResponse({"error": "not_authenticated"}, status_code=401)


def _dev_mode() -> bool:
    return os.environ.get("MEMAIX_DEV", "") == "1"


def _read_page(page: str) -> str:
    if not _dev_mode() and page in _HTML_CACHE:
        return _HTML_CACHE[page]
    path = _PAGES / f"{page}.html"
    raw = path.read_text(encoding="utf-8")  # FileNotFoundError → 404 in handler
    if not _dev_mode():
        _HTML_CACHE[page] = raw
    return raw


_ASSET_VERSIONS: dict[str, str] = {}
_ASSET_REF = re.compile(r"/app/static/([A-Za-z0-9_.\-/]+)")


def _asset_version(rel: str) -> str | None:
    """Short content hash for static/{rel}, or None if the file is missing."""
    if not _dev_mode() and rel in _ASSET_VERSIONS:
        return _ASSET_VERSIONS[rel]
    target = (_STATIC / rel).resolve()
    if not target.is_relative_to(_STATIC.resolve()) or not target.is_file():
        return None
    digest = hashlib.sha256(target.read_bytes()).hexdigest()[:12]
    if not _dev_mode():
        _ASSET_VERSIONS[rel] = digest
    return digest


def _version_assets(html: str) -> str:
    """Rewrite /app/static/x → /app/static/x?v=<hash> so CDN/browser caches
    can hold assets long-term yet pick up new code on the next page load
    (pages themselves are served no-cache)."""

    def sub(m: re.Match) -> str:
        version = _asset_version(m.group(1))
        return m.group(0) if version is None else f"{m.group(0)}?v={version}"

    return _ASSET_REF.sub(sub, html)


def _html_with_locale(page: str, locale: str) -> str:
    """Render pages/{page}.html inside the shell with i18n strings injected."""
    shell = _read_page("shell")
    content = _read_page(page)
    html = shell.replace("<!--MEMAIX_CONTENT-->", content, 1)
    from ..i18n import _load

    strings = _load(locale)
    inject = f"<script>window.I18N={json.dumps(strings, ensure_ascii=False)};</script>"
    return _version_assets(html.replace("<!--MEMAIX_I18N-->", inject, 1))


def _locale(request: Request) -> str:
    return locale_from_request(request.headers.get("Accept-Language"), _config_locale())


# Dark-theme override injected into the embedded board frame: board.html styles
# itself with :root custom properties, so re-declaring them after its own
# stylesheet flips the palette without touching board.html (shell and board
# read as one dark application, FEATURE-WEB-UI-FOUNDATION.md §1).
_BOARD_DARK_STYLE = (
    "<style>:root{--bg:#0f1117;--surface:#1a1d27;--border:#2d3044;"
    "--text:#e2e8f0;--muted:#94a3b8;--card-shadow:0 1px 3px rgba(0,0,0,.5)}</style>"
)


class BrowserRootRedirect:
    """ASGI wrapper: send browsers landing on "/" to the web UI at /app.

    The MCP endpoint is mounted at root so claude.ai finds it at the connector
    URL directly (server.py::build_http_app), which means a human typing the
    bare domain into a browser gets the MCP 401 JSON. Only the narrowest
    browser signature is diverted — GET "/" with no Authorization header and
    text/html in Accept. MCP/API clients never send text/html (streamable
    HTTP GET uses text/event-stream), so they pass through untouched.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"] == "/" and scope["method"] == "GET":
            headers = {
                k.decode("latin-1").lower(): v.decode("latin-1")
                for k, v in scope.get("headers", [])
            }
            if "authorization" not in headers and "text/html" in headers.get("accept", ""):
                await RedirectResponse("/app", status_code=302)(scope, receive, send)
                return
        await self.app(scope, receive, send)


# ------------------------------------------------------------------
# Page routes
# ------------------------------------------------------------------


async def app_index(request: Request) -> HTMLResponse:
    return HTMLResponse(
        _html_with_locale("home", _locale(request)),
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


async def app_login(request: Request) -> HTMLResponse:
    """GET /app/login — standalone login page (no shell wrapper).

    Cookie-based login for the web UI; redirects to ?next= on success.
    Distinct from /login which is the Hydra OAuth flow for MCP clients.
    """
    locale = _locale(request)
    from ..i18n import _load
    strings = _load(locale)
    inject = f"<script>window.I18N={json.dumps(strings, ensure_ascii=False)};</script>"
    raw = _read_page("login")
    html = _version_assets(raw.replace("<!--MEMAIX_I18N-->", inject, 1))
    return HTMLResponse(html, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


async def app_page(request: Request) -> Response:
    page = request.path_params["page"]
    if page not in _KNOWN_PAGES:
        return JSONResponse({"error": "not_found"}, status_code=404)
    try:
        html = _html_with_locale(page, _locale(request))
    except FileNotFoundError:
        return JSONResponse({"error": "not_found"}, status_code=404)
    return HTMLResponse(html, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


async def app_board_frame(request: Request) -> HTMLResponse:
    """The original board UI, served for embedding in the shell's iframe.

    /board itself is a 301 to /app/board, so the iframe needs a non-redirecting
    source; the board's own /board/api/* routes are untouched and keep working
    inside the frame (same origin, same cookie).
    """
    html = _board_html_with_locale(_locale(request))
    html = html.replace("</head>", _BOARD_DARK_STYLE + "</head>", 1)
    return HTMLResponse(html, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


async def app_static(request: Request) -> Response:
    rel = request.path_params["path"]
    target = (_STATIC / rel).resolve()
    # Path-traversal guard: the resolved target must stay inside static/.
    if not target.is_relative_to(_STATIC.resolve()) or not target.is_file():
        return JSONResponse({"error": "not_found"}, status_code=404)
    media_type = _STATIC_TYPES.get(target.suffix, "application/octet-stream")
    # Versioned URLs (?v=<hash>) are immutable; bare URLs must revalidate so
    # a CDN in front (Cloudflare defaults to 4h for .js/.css) never pins an
    # old asset after deploy.
    cache = (
        "public, max-age=31536000, immutable"
        if request.query_params.get("v")
        else "no-cache"
    )
    return FileResponse(target, media_type=media_type, headers={"Cache-Control": cache})


async def board_redirect(request: Request) -> Response:
    """GET /board → 301 /app/board (preserves query params, keeps bookmarks)."""
    qs = request.url.query
    target = "/app/board" + (f"?{qs}" if qs else "")
    return Response(status_code=301, headers={"Location": target})


# ------------------------------------------------------------------
# JSON API
# ------------------------------------------------------------------


async def api_me(request: Request) -> JSONResponse:
    """GET /app/api/me — user identity + roles + project status. 401 unless
    authenticated. The single source all role-aware page JS builds on."""
    user = _require_user(request)
    if not user:
        return _json_401()

    acl = _get_acl()
    projects = acl.visible_projects(user)
    is_admin = acl.is_admin(user)
    grants = acl.grants(user)
    role_map = {p: ("admin" if is_admin else grants.get(p, "")) for p in projects}

    needs_relink: list[str] = []
    if os.environ.get("MEMAIX_TOKEN_DB", ""):
        try:
            from ..server import _get_token_store

            store = _get_token_store()
            needs_relink = sorted(
                {a["provider"] for a in store.list_accounts(user) if a["status"] == "needs_relink"}
            )
        except Exception:
            needs_relink = []  # token store unavailable — not this endpoint's failure

    return JSONResponse(
        {
            "user": user,
            "is_admin": is_admin,
            "role_map": role_map,
            "projects": projects,
            "needs_relink": needs_relink,
            "pending_outbox": _pending_outbox_count(acl, user),
            "onboarding_missing": _onboarding_missing(acl, user, projects),
        }
    )


def _pending_outbox_count(acl, user: str) -> int:
    """Pending outbox actions THIS user can approve (approver-scoped, same rule
    as the MCP outbox_list — a reader must not even learn the count)."""
    try:
        from ..outbox.queue import ActionQueue
        from ..server import _can_approve_action

        db_path = Path(os.environ.get("MEMAIX_OUTBOX_DB", "/tmp/memaix-outbox.db"))  # nosec B108 -- same default as board/routes
        queue = ActionQueue.for_path(db_path)
        actions = queue.list(acl.visible_projects(user), "pending")
        return sum(1 for a in actions if _can_approve_action(acl, user, a))
    except Exception:
        return 0  # outbox unavailable — dashboard must still render


def _onboarding_missing(acl, user: str, projects: list[str]) -> bool:
    """True if any visible project's vault says this user still needs onboarding."""
    try:
        from ..tools.onboarding import check_onboarding

        for project in projects:
            vault = acl.resource(project, "vault")
            if not vault or not Path(vault).is_dir():
                continue  # unprovisioned vault ≠ missing onboarding
            if check_onboarding(user, Path(vault)).get("needs_onboarding"):
                return True
    except Exception:
        pass  # advisory only — never block /app/api/me
    return False


# ------------------------------------------------------------------
# Route table (mounted in server.build_http_app beside board_routes)
# ------------------------------------------------------------------

# Imported at the bottom on purpose: the api modules import _require_user &
# friends from this module, so they must load after those are defined.
from .api import accounts as _api_accounts  # noqa: E402
from .api import admin as _api_admin  # noqa: E402
from .api import admin_write as _api_admin_write  # noqa: E402
from .api import brief as _api_brief  # noqa: E402
from .api import memory as _api_memory  # noqa: E402
from .api import mfa as _api_mfa  # noqa: E402
from .api import outbox as _api_outbox  # noqa: E402
from .api import search as _api_search  # noqa: E402
from .api import timeline as _api_timeline  # noqa: E402

web_routes = [
    Route("/app", app_index, methods=["GET"]),
    Route("/app/login", app_login, methods=["GET"]),
    Route("/app/api/me", api_me, methods=["GET"]),
    # Search / brief / timeline (FEATURE-WEB-UI-PHASE2.md, Fas D)
    Route("/app/api/search", _api_search.api_search, methods=["GET"]),
    Route("/app/api/brief", _api_brief.api_brief_get, methods=["GET"]),
    Route("/app/api/brief", _api_brief.api_brief_set, methods=["POST"]),
    Route("/app/api/timeline", _api_timeline.api_timeline, methods=["GET"]),
    Route("/app/api/timeline/{id}/undo", _api_timeline.api_timeline_undo, methods=["POST"]),
    # MFA + admin write (Fas D — MFA-gated)
    Route("/app/api/admin/mfa", _api_mfa.api_mfa_status, methods=["GET"]),
    Route("/app/api/admin/mfa/setup/start", _api_mfa.api_mfa_setup_start, methods=["POST"]),
    Route("/app/api/admin/mfa/setup", _api_mfa.api_mfa_setup_confirm, methods=["POST"]),
    Route("/app/api/admin/mfa/verify", _api_mfa.api_mfa_verify, methods=["POST"]),
    Route("/app/api/admin/users/{uid}", _api_admin_write.api_admin_set_disabled, methods=["PATCH"]),
    Route("/app/api/admin/users/{uid}/grants", _api_admin_write.api_admin_set_grants, methods=["PATCH"]),
    Route("/app/api/admin/projects/{project}", _api_admin_write.api_admin_set_project_field, methods=["PATCH"]),
    # Outbox — approver-scoped (FEATURE-WEB-UI-OUTBOX-AND-ADMIN.md, Fas C)
    Route("/app/api/outbox", _api_outbox.api_outbox_list, methods=["GET"]),
    Route("/app/api/outbox/{id}", _api_outbox.api_outbox_get, methods=["GET"]),
    Route("/app/api/outbox/{id}/approve", _api_outbox.api_outbox_approve, methods=["POST"]),
    Route("/app/api/outbox/{id}/reject", _api_outbox.api_outbox_reject, methods=["POST"]),
    # Admin read views (Fas C)
    Route("/app/api/admin/users", _api_admin.api_admin_users, methods=["GET"]),
    Route("/app/api/admin/projects", _api_admin.api_admin_projects, methods=["GET"]),
    Route("/app/api/admin/audit", _api_admin.api_admin_audit, methods=["GET"]),
    Route("/app/api/admin/system", _api_admin.api_admin_system, methods=["GET"]),
    # Memory explorer (FEATURE-WEB-UI-MVP.md §4.4)
    Route("/app/api/memory/notes", _api_memory.api_memory_notes, methods=["GET"]),
    Route("/app/api/memory/note", _api_memory.api_memory_note, methods=["GET"]),
    Route("/app/api/memory/search", _api_memory.api_memory_search, methods=["GET"]),
    Route("/app/api/memory/history", _api_memory.api_memory_history, methods=["GET"]),
    Route("/app/api/memory/revert", _api_memory.api_memory_revert, methods=["POST"]),
    # Accounts + calendar mode (FEATURE-WEB-UI-MVP.md §4.5)
    Route("/app/api/accounts", _api_accounts.api_accounts_list, methods=["GET"]),
    Route("/app/api/accounts/link/{provider}", _api_accounts.api_accounts_link, methods=["GET"]),
    Route("/app/api/accounts/{provider}", _api_accounts.api_accounts_unlink, methods=["DELETE"]),
    Route("/app/api/settings/calendar-mode", _api_accounts.api_calendar_mode_get, methods=["GET"]),
    Route("/app/api/settings/calendar-mode", _api_accounts.api_calendar_mode_set, methods=["POST"]),
    Route("/app/board/frame", app_board_frame, methods=["GET"]),
    Route("/app/static/{path:path}", app_static, methods=["GET"]),
    Route("/app/{page:str}", app_page, methods=["GET"]),
    Route("/board", board_redirect, methods=["GET"]),
]
