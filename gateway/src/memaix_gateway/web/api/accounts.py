# SPDX-License-Identifier: AGPL-3.0-or-later
"""Web API for account linking + calendar mode — thin layer over
tools/account.py and tools/calendar.py."""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse

from ...acl import AccessDenied
from ...tools import account as t_acc
from ...tools import calendar as t_cal
from .. import routes as w


# Resolved through the routes module at call time (not import-time binding) so
# there is exactly one auth/acl seam — tests patch web.routes and every api
# module follows.
def _require_user(request: Request) -> str | None:
    return w._require_user(request)


def _get_acl():
    return w._get_acl()


def _json_401() -> JSONResponse:
    return w._json_401()


def _token_store():
    from ...server import _get_token_store

    return _get_token_store()


def _public_url() -> str:
    from ... import config

    return config.load().get("memaix", {}).get("server", {}).get("public_url", "")


async def api_accounts_list(request: Request) -> JSONResponse:
    """GET /app/api/accounts → [{provider, account, status, scopes}]"""
    user = _require_user(request)
    if not user:
        return _json_401()
    return JSONResponse(t_acc.account_list(_get_acl(), user, _token_store()))


async def api_accounts_link(request: Request) -> JSONResponse:
    """GET /app/api/accounts/link/{provider} → {url} (opened in a new window)"""
    user = _require_user(request)
    if not user:
        return _json_401()
    provider = request.path_params["provider"]
    try:
        result = t_acc.account_link(_get_acl(), user, provider, _public_url())
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse({"url": result.get("link_url", "")})


async def api_accounts_unlink(request: Request) -> JSONResponse:
    """DELETE /app/api/accounts/{provider}?account=X → {ok}"""
    user = _require_user(request)
    if not user:
        return _json_401()
    provider = request.path_params["provider"]
    account = request.query_params.get("account", "")
    try:
        result = t_acc.account_unlink(_get_acl(), user, provider, account, _token_store())
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except FileNotFoundError:
        return JSONResponse({"error": "not_found"}, status_code=404)
    return JSONResponse(result)


async def api_calendar_mode_get(request: Request) -> JSONResponse:
    """GET /app/api/settings/calendar-mode?project=X → {active_mode, details, available_modes}"""
    user = _require_user(request)
    if not user:
        return _json_401()
    project = request.query_params.get("project", "")
    try:
        status = t_cal.get_status(user, project, _get_acl(), _token_store())
    except AccessDenied:
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return JSONResponse(status)


async def api_calendar_mode_set(request: Request) -> JSONResponse:
    """POST /app/api/settings/calendar-mode {project, mode, ical_url?, calendar_id?}"""
    user = _require_user(request)
    if not user:
        return _json_401()
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "bad_request"}, status_code=400)
    try:
        result = t_cal.setup_mode(
            _get_acl(), user, body.get("project", ""), body.get("mode", ""),
            _token_store(), _public_url(),
            ical_url=body.get("ical_url"), calendar_id=body.get("calendar_id"),
        )
    except AccessDenied:
        return JSONResponse({"error": "forbidden"}, status_code=403)
    status = 200 if result.get("ok") else 400
    return JSONResponse(result, status_code=status)
