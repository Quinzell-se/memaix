# SPDX-License-Identifier: AGPL-3.0-or-later
"""Public meeting-booking routes — memaix-src card 2bef1062.

Unauthenticated surface (no login, no ACL grant on the visitor) that lets
anyone holding a booking-link slug (links.py) see a host's free slots and
book one. Mirrors the unauthenticated-route pattern established by
rule_webhook (server.py) — rate-limited per client IP, the slug plays the
same "token IS the capability" role rule_webhook's token does.

The host's own ACL-provisioned user_id (from the link record) is used for
every calendar_* call, so calendar_find_free/calendar_create's existing
"collaborator" enforcement is satisfied naturally — there is no anonymous
bypass in tools/calendar.py and this route does not attempt to add one.

Privacy: only ever returns {start, end} slots (memaix-src card de858332) —
never calendar_free_busy's richer, source-tagged view.

CORS is scoped to these four routes only (not the whole app), since
jimlov.se is a static export with no server runtime and must call this
gateway cross-origin.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import config
from ..tools import calendar as t_cal
from ..tools.calendar import CalendarAuthRequired
from .links import get_link

_ALLOWED_ORIGINS = {"https://jimlov.se", "https://www.jimlov.se"}
_TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
_MIN_DURATION_MIN = 15
_MAX_DURATION_MIN = 240
_MAX_WINDOW_DAYS = 30


def _get_acl():
    # Lazy indirection to server's cached Acl, same pattern as web/routes.py —
    # function-level import avoids a module-import cycle with server.py.
    from ..server import _get_acl as _srv_get_acl

    return _srv_get_acl()


def _resolve_dav(project: str, user: str):
    from ..server import _resolve_calendar_dav as _srv_resolve_dav

    return _srv_resolve_dav(project, user)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _cors_headers(request: Request) -> dict:
    origin = request.headers.get("origin", "")
    if origin not in _ALLOWED_ORIGINS:
        return {}
    return {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Vary": "Origin",
    }


def _json(request: Request, payload: dict, status_code: int = 200) -> JSONResponse:
    return JSONResponse(payload, status_code=status_code, headers=_cors_headers(request))


def _clamp_duration(duration_min: int) -> int:
    return max(_MIN_DURATION_MIN, min(_MAX_DURATION_MIN, duration_min))


def _parse_dt(value: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _clamp_window(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    cap = start + timedelta(days=_MAX_WINDOW_DAYS)
    return start, min(end, cap)


async def _verify_turnstile(token: str, remote_ip: str) -> bool:
    """Fail-closed: no secret configured -> refuse, never silently allow
    through. Captcha is mandatory for this public surface, not optional."""
    cfg = config.load()
    secret_ref = cfg.get("memaix", {}).get("booking", {}).get("turnstile_secret_ref")
    if not secret_ref:
        return False
    try:
        secret = config.secret(secret_ref)
    except (KeyError, NotImplementedError):
        return False
    if not token:
        return False
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                _TURNSTILE_VERIFY_URL,
                data={"secret": secret, "response": token, "remoteip": remote_ip},
                timeout=10.0,
                follow_redirects=False,
            )
        resp.raise_for_status()
        return bool(resp.json().get("success"))
    except httpx.HTTPError:
        return False


async def booking_slots(request: Request) -> JSONResponse:
    """GET /book/{slug}/slots?within_start=&within_end=&duration_min= —
    free {start, end} windows only, never event details or which calendar
    source they came from (card de858332)."""
    client_ip = _client_ip(request)
    if not _rate_limiter().check(f"booking:{client_ip}", limit=30, window_s=60):
        return _json(request, {"error": "rate_limited"}, status_code=429)

    link = get_link(request.path_params["slug"])
    if link is None:
        return _json(request, {"error": "not_found"}, status_code=404)

    acl = _get_acl()
    project, host_user = link["project"], link["user"]
    enabled = t_cal.calendar_booking_enabled_get(acl, host_user, project)
    if not enabled.get("enabled"):
        return _json(request, {"error": "not_found"}, status_code=404)

    q = request.query_params
    duration_min = _clamp_duration(int(q.get("duration_min") or link.get("duration_min", 30)))
    within_start = _parse_dt(q.get("within_start", ""))
    within_end = _parse_dt(q.get("within_end", ""))
    if within_start is None or within_end is None or within_end <= within_start:
        return _json(request, {"error": "invalid_window"}, status_code=400)
    within_start, within_end = _clamp_window(within_start, within_end)

    try:
        dav = _resolve_dav(project, host_user)
        slots = t_cal.calendar_find_free(
            acl, host_user, project, duration_min,
            within_start.isoformat(), within_end.isoformat(), _dav=dav,
        )
    except CalendarAuthRequired:
        return _json(request, {"error": "not_found"}, status_code=404)

    return _json(request, {"slots": slots, "duration_min": duration_min})


async def booking_create(request: Request) -> JSONResponse:
    """POST /book/{slug} — {start, end, name, email, turnstile_token}."""
    client_ip = _client_ip(request)
    if not _rate_limiter().check(f"booking:{client_ip}", limit=10, window_s=60):
        return _json(request, {"error": "rate_limited"}, status_code=429)

    link = get_link(request.path_params["slug"])
    if link is None:
        return _json(request, {"error": "not_found"}, status_code=404)

    try:
        body = await request.json()
    except Exception:
        body = {}

    if not isinstance(body, dict):
        return _json(request, {"error": "invalid_body"}, status_code=400)

    if not await _verify_turnstile(str(body.get("turnstile_token") or ""), client_ip):
        return _json(request, {"error": "captcha_failed"}, status_code=403)

    name = str(body.get("name") or "").strip()
    email = str(body.get("email") or "").strip()
    start = _parse_dt(str(body.get("start") or ""))
    end = _parse_dt(str(body.get("end") or ""))
    if not name or not email or start is None or end is None or end <= start:
        return _json(request, {"error": "invalid_body"}, status_code=400)

    duration = end - start
    if not (timedelta(minutes=_MIN_DURATION_MIN) <= duration <= timedelta(minutes=_MAX_DURATION_MIN)):
        return _json(request, {"error": "invalid_duration"}, status_code=400)

    acl = _get_acl()
    project, host_user = link["project"], link["user"]
    enabled = t_cal.calendar_booking_enabled_get(acl, host_user, project)
    if not enabled.get("enabled"):
        return _json(request, {"error": "not_found"}, status_code=404)

    try:
        dav = _resolve_dav(project, host_user)
    except CalendarAuthRequired:
        return _json(request, {"error": "not_found"}, status_code=404)

    # First-line TOCTOU defense only, not a lock — a second visitor racing
    # for the same slot between this check and calendar_create below can
    # still win. Real fix (locking/optimistic-conflict handling) is
    # memaix-src card d99e2840, deliberately out of scope here.
    # calendar_find_free only returns a slot whose window is strictly
    # longer than the requested duration (see its "we > cursor + duration"
    # check) — pad the query window by a minute so an exact-fit free block
    # still shows up here.
    still_free = t_cal.calendar_find_free(
        acl, host_user, project, int(duration.total_seconds() // 60),
        start.isoformat(), (end + timedelta(minutes=1)).isoformat(), _dav=dav,
    )
    def _covers(s: dict) -> bool:
        s_start, s_end = _parse_dt(s.get("start", "")), _parse_dt(s.get("end", ""))
        # Unparseable start/end -> not a usable free slot. Never crash the
        # public handler on a malformed calendar row; treat it as no cover.
        if s_start is None or s_end is None:
            return False
        return s_start <= start and s_end >= end

    if not any(_covers(s) for s in still_free):
        return _json(request, {"error": "slot_unavailable"}, status_code=409)

    title = link.get("title_template", "Möte").format(name=name) if "{name}" in link.get("title_template", "") else link.get("title_template", "Möte")
    event = t_cal.calendar_create(
        acl, host_user, project, title,
        start.isoformat(), end.isoformat(),
        attendees=[email], _dav=dav, _confirmed=True,
    )
    return _json(request, {"ok": True, "start": event.get("start"), "end": event.get("end")})


async def booking_options(request: Request) -> Response:
    return Response(status_code=204, headers=_cors_headers(request))


def _rate_limiter():
    from ..safety.rate_limit import rate_limiter

    return rate_limiter


booking_routes = [
    Route("/book/{slug}/slots", booking_slots, methods=["GET"]),
    Route("/book/{slug}/slots", booking_options, methods=["OPTIONS"]),
    Route("/book/{slug}", booking_create, methods=["POST"]),
    Route("/book/{slug}", booking_options, methods=["OPTIONS"]),
]
