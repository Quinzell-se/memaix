# SPDX-License-Identifier: AGPL-3.0-or-later
"""Kanban board — Starlette route handlers."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from pathlib import Path

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

from ..acl import Acl, AccessDenied
from ..i18n import get_translator, locale_from_request
from ..safety.audit import AuditLog
from . import store as s

_BOARD_HTML = Path(__file__).parent / "board.html"
_BOARD_HTML_RAW: str | None = None


def _board_html_with_locale(locale: str) -> str:
    global _BOARD_HTML_RAW
    if _BOARD_HTML_RAW is None:
        _BOARD_HTML_RAW = _BOARD_HTML.read_text(encoding="utf-8")
    from ..i18n import _load
    strings = _load(locale)
    inject = f'<script>window.I18N={json.dumps(strings, ensure_ascii=False)};</script>'
    return _BOARD_HTML_RAW.replace("<!--MEMAIX_I18N-->", inject, 1)
_ALLOWED_USERS: set[str] = set(
    os.environ.get("MEMAIX_ALLOWED_USERS", "alice").split(",")
)
_PASSWORD_HASH = os.environ.get("MEMAIX_LOGIN_PASSWORD_HASH", "")
_COOKIE_NAME = "memaix_board"
_COOKIE_TTL_DAYS = 1


def _secret() -> bytes:
    raw = os.environ.get("HYDRA_SYSTEM_SECRET", "dev-secret-change-me")
    return raw.encode()[:32].ljust(32, b"0")


def _verify_password(provided: str) -> bool:
    if not _PASSWORD_HASH or ":" not in _PASSWORD_HASH:
        return False
    salt_hex, key_hex = _PASSWORD_HASH.split(":", 1)
    salt = bytes.fromhex(salt_hex)
    derived = hashlib.pbkdf2_hmac("sha256", provided.encode(), salt, 200_000)
    return hmac.compare_digest(derived.hex(), key_hex)


def _make_cookie(user: str) -> str:
    day = int(time.time()) // 86400
    sig = hmac.new(_secret(), f"{user}:{day}".encode(), "sha256").hexdigest()[:32]
    return f"{user}:{day}:{sig}"


def _check_cookie(request: Request) -> str | None:
    raw = request.cookies.get(_COOKIE_NAME, "")
    parts = raw.split(":")
    if len(parts) != 3:
        return None
    user, day_str, sig = parts
    try:
        day = int(day_str)
    except ValueError:
        return None
    today = int(time.time()) // 86400
    if abs(today - day) > _COOKIE_TTL_DAYS:
        return None
    expected = hmac.new(_secret(), f"{user}:{day}".encode(), "sha256").hexdigest()[:32]
    if not hmac.compare_digest(sig, expected):
        return None
    if user not in _ALLOWED_USERS:
        return None
    return user


def _acl() -> Acl:
    from .. import config
    from ..acl import Acl
    cfg = config.load()
    return Acl.from_config(cfg["acl"])


def _user_projects(user: str, acl: Acl) -> list[str]:
    return acl.visible_projects(user)


def _audit() -> AuditLog:
    db_path = Path(os.environ.get("MEMAIX_AUDIT_DB", "/tmp/memaix-audit.db"))
    return AuditLog.for_path(db_path)


# ------------------------------------------------------------------
# Auth routes
# ------------------------------------------------------------------


def _config_locale() -> str:
    try:
        from .. import config
        return config.load().get("memaix", {}).get("server", {}).get("locale", "en")
    except Exception:
        return "en"


async def board_index(request: Request) -> HTMLResponse:
    locale = locale_from_request(
        request.headers.get("Accept-Language"),
        _config_locale(),
    )
    return HTMLResponse(
        _board_html_with_locale(locale),
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


async def board_login(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "bad request"}, status_code=400)

    username = body.get("username", "").strip()
    password = body.get("password", "")

    if username not in _ALLOWED_USERS or not _verify_password(password):
        return JSONResponse({"error": "invalid credentials"}, status_code=401)

    resp = JSONResponse({"ok": True, "user": username})
    resp.set_cookie(
        _COOKIE_NAME, _make_cookie(username),
        httponly=True, samesite="lax", secure=True, max_age=86400 * _COOKIE_TTL_DAYS,
    )
    return resp


async def board_logout(request: Request) -> JSONResponse:
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(_COOKIE_NAME)
    return resp


# ------------------------------------------------------------------
# API helpers
# ------------------------------------------------------------------


def _require_user(request: Request) -> str | None:
    return _check_cookie(request)


def _json_401() -> JSONResponse:
    return JSONResponse({"error": "not authenticated"}, status_code=401)


def _json_403() -> JSONResponse:
    return JSONResponse({"error": "access denied"}, status_code=403)


# ------------------------------------------------------------------
# API routes
# ------------------------------------------------------------------


async def api_projects(request: Request) -> JSONResponse:
    user = _require_user(request)
    if not user:
        return _json_401()
    acl = _acl()
    return JSONResponse({"user": user, "projects": _user_projects(user, acl)})


async def api_board(request: Request) -> JSONResponse:
    user = _require_user(request)
    if not user:
        return _json_401()

    project = request.query_params.get("project", "")
    sprint_filter = request.query_params.get("sprint", "")
    acl = _acl()

    if project not in _user_projects(user, acl):
        return _json_403()

    vault_str = acl.resource(project, "vault")
    if not vault_str:
        return JSONResponse({"error": "no vault for project"}, status_code=404)
    vault = Path(vault_str)

    cards = s.list_backlog(vault)

    # Sprint filter
    active_sprint_id = None
    if sprint_filter:
        sprints, detected_active = s.list_sprints(vault)
        if sprint_filter == "active":
            active_sprint_id = detected_active
            if active_sprint_id:
                sprint_items = next(
                    (sp["items"] for sp in sprints if sp["id"] == active_sprint_id), []
                )
                cards = [c for c in cards if c["id"] in sprint_items]
        else:
            sprint_items_set: set[str] = set()
            for sp in sprints:
                if sp["id"] == sprint_filter:
                    sprint_items_set = set(sp["items"])
                    active_sprint_id = sp["id"]
                    break
            if not sprint_items_set and sprint_filter:
                return JSONResponse({"error": f"unknown sprint: {sprint_filter}"}, status_code=400)
            if sprint_items_set:
                cards = [c for c in cards if c["id"] in sprint_items_set]

    # Group into columns, sort by value desc then updated_at desc
    col_map: dict[str, list[dict]] = {key: [] for key, _ in s.COLUMNS}
    for card in cards:
        st = card.get("status", "inbox")
        if st in col_map:
            col_map[st].append(card)
        else:
            col_map["inbox"].append(card)

    def _sort_key(c: dict):
        v = c.get("value") or 0
        return (-v, c.get("updated_at", ""))

    columns = [
        {
            "key":   key,
            "label": label,
            "muted": key == "rejected",
            "cards": sorted(col_map[key], key=_sort_key),
        }
        for key, label in s.COLUMNS
    ]

    return JSONResponse({
        "project":        project,
        "sprint":         active_sprint_id or sprint_filter or None,
        "columns":        columns,
        "total_cards":    len(cards),
    })


async def api_sprints(request: Request) -> JSONResponse:
    user = _require_user(request)
    if not user:
        return _json_401()

    project = request.query_params.get("project", "")
    acl = _acl()
    if project not in _user_projects(user, acl):
        return _json_403()

    vault_str = acl.resource(project, "vault")
    if not vault_str:
        return JSONResponse({"sprints": [], "active": None})

    sprints, active = s.list_sprints(Path(vault_str))
    return JSONResponse({"sprints": sprints, "active": active})


async def api_item(request: Request) -> JSONResponse:
    user = _require_user(request)
    if not user:
        return _json_401()

    item_id = request.path_params["id"]
    project = request.query_params.get("project", "")
    acl = _acl()
    if project not in _user_projects(user, acl):
        return _json_403()

    vault_str = acl.resource(project, "vault")
    if not vault_str:
        return JSONResponse({"error": "no vault"}, status_code=404)

    item = s.get_item(Path(vault_str), item_id)
    if item is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(item)


async def api_item_patch(request: Request) -> JSONResponse:
    user = _require_user(request)
    if not user:
        return _json_401()

    item_id = request.path_params["id"]
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "bad request"}, status_code=400)

    project = body.get("project", "")
    new_status = body.get("status", "")
    acl = _acl()

    if project not in _user_projects(user, acl):
        return _json_403()

    # Moving a card is a status transition — same authority as the MCP tool
    # backlog_set_status, which requires owner. Readers/collaborators may view
    # the board but must not mutate item state through it.
    try:
        acl.enforce(user, project, "owner")
    except AccessDenied:
        return _json_403()

    vault_str = acl.resource(project, "vault")
    if not vault_str:
        return JSONResponse({"error": "no vault"}, status_code=404)

    try:
        card = s.write_status(Path(vault_str), item_id, new_status)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except FileNotFoundError as e:
        return JSONResponse({"error": str(e)}, status_code=404)

    old = card.pop("_old_status", "?")
    try:
        _audit().log(user, project, "board_move", True, f"{item_id}: {old} → {new_status}")
    except Exception:
        pass

    return JSONResponse({"ok": True, "item": card})


async def api_activity(request: Request) -> JSONResponse:
    user = _require_user(request)
    if not user:
        return _json_401()

    project = request.query_params.get("project", "")
    since = request.query_params.get("since", "")
    acl = _acl()

    try:
        events = _audit().tail(limit=50)
    except Exception:
        return JSONResponse({"events": []})

    if project:
        # Only show events for projects this user can read
        allowed = set(_user_projects(user, acl))
        events = [e for e in events if e["project"] == project and project in allowed]
    else:
        allowed = set(_user_projects(user, acl))
        events = [e for e in events if e["project"] in allowed]

    if since:
        events = [e for e in events if e["ts"] > since]

    return JSONResponse({"events": events})


# ------------------------------------------------------------------
# Route table
# ------------------------------------------------------------------

board_routes = [
    Route("/board",                 board_index,      methods=["GET"]),
    Route("/board/auth/login",      board_login,      methods=["POST"]),
    Route("/board/auth/logout",     board_logout,     methods=["POST"]),
    Route("/board/api/projects",    api_projects,     methods=["GET"]),
    Route("/board/api/board",       api_board,        methods=["GET"]),
    Route("/board/api/sprints",     api_sprints,      methods=["GET"]),
    Route("/board/api/item/{id}",   api_item,         methods=["GET"]),
    Route("/board/api/item/{id}",   api_item_patch,   methods=["PATCH"]),
    Route("/board/api/activity",    api_activity,     methods=["GET"]),
]
