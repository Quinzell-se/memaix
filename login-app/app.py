# SPDX-License-Identifier: AGPL-3.0-or-later
"""Minimal Hydra login/consent-app för Memaix.

Hanterar:
  GET  /login    — visa inloggningsformulär
  POST /login    — verifiera lösenord, godkänn eller neka hos Hydra
  GET  /consent  — auto-godkänn (single-user, trusted client)

Säkra standarder:
  - Lösenord verifieras med PBKDF2-HMAC-SHA256 (200 000 iterationer)
  - Hydra challenge valideras innan formuläret visas
  - Inget session state lagras i appen — Hydra håller session
"""

from __future__ import annotations

import hashlib
import hmac
import os
import sys
from urllib.parse import urlencode

import requests
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

sys.path.insert(0, "/app/i18n_pkg")
try:
    from memaix_gateway.i18n import get_translator, locale_from_request as _locale_from_req
    _I18N_AVAILABLE = True
except ImportError:
    _I18N_AVAILABLE = False


def _t_for_request(request: Request):
    if not _I18N_AVAILABLE:
        return lambda k: k, "en"
    locale = _locale_from_req(
        request.headers.get("Accept-Language"),
        os.environ.get("MEMAIX_LOCALE", "en"),
    )
    return get_translator(locale), locale

HYDRA_ADMIN = os.environ.get("HYDRA_ADMIN_URL", "http://hydra:4445")
ALLOWED_USERS: set[str] = set(
    os.environ.get("MEMAIX_ALLOWED_USERS", "alice").split(",")
)
# Shared fallback hash (single-user backwards-compat). Format: salt_hex:pbkdf2_hex
_SHARED_HASH = os.environ.get("MEMAIX_LOGIN_PASSWORD_HASH", "")

# Per-user hashes from acl.yaml (users.<id>.password_hash). Loaded at startup.
_PER_USER_HASHES: dict[str, str] = {}

_ACL_PATH = os.environ.get("MEMAIX_ACL_CONFIG", "/app/config/acl.yaml")


def _load_per_user_hashes() -> None:
    try:
        import yaml
        with open(_ACL_PATH) as f:
            acl = yaml.safe_load(f) or {}
        for uid, udata in (acl.get("users") or {}).items():
            h = (udata or {}).get("password_hash", "")
            if h:
                _PER_USER_HASHES[uid] = h
    except Exception:
        pass  # acl.yaml missing or unparseable — fall back to shared hash


_load_per_user_hashes()

app = FastAPI(title="Memaix login")
templates = Jinja2Templates(directory="/app/templates")


def _pbkdf2_check(provided: str, stored_hash: str) -> bool:
    if not stored_hash or ":" not in stored_hash:
        return False
    salt_hex, key_hex = stored_hash.split(":", 1)
    salt = bytes.fromhex(salt_hex)
    derived = hashlib.pbkdf2_hmac("sha256", provided.encode(), salt, 200_000)
    return hmac.compare_digest(derived.hex(), key_hex)


def _verify_password(user: str, provided: str) -> bool:
    per_user = _PER_USER_HASHES.get(user)
    if per_user:
        return _pbkdf2_check(provided, per_user)
    return _pbkdf2_check(provided, _SHARED_HASH)


def _hydra_get(path: str, challenge_name: str, challenge: str) -> dict:
    r = requests.get(
        f"{HYDRA_ADMIN}{path}",
        params={challenge_name: challenge},
        timeout=5,
    )
    r.raise_for_status()
    return r.json()


def _hydra_accept(path: str, challenge_name: str, challenge: str, body: dict) -> str:
    r = requests.put(
        f"{HYDRA_ADMIN}{path}",
        params={challenge_name: challenge},
        json=body,
        timeout=5,
    )
    r.raise_for_status()
    return r.json()["redirect_to"]


def _hydra_reject(path: str, challenge_name: str, challenge: str, reason: str) -> str:
    r = requests.put(
        f"{HYDRA_ADMIN}{path}",
        params={challenge_name: challenge},
        json={"error": "access_denied", "error_description": reason},
        timeout=5,
    )
    r.raise_for_status()
    return r.json()["redirect_to"]


# ------------------------------------------------------------------
# Login
# ------------------------------------------------------------------


@app.get("/login", response_class=HTMLResponse)
async def login_get(request: Request, login_challenge: str = ""):
    if not login_challenge:
        return HTMLResponse("<p>Ogiltig förfrågan (login_challenge saknas).</p>", status_code=400)
    try:
        info = _hydra_get("/admin/oauth2/auth/requests/login", "login_challenge", login_challenge)
    except Exception as exc:
        return HTMLResponse(f"<p>Hydra-fel: {exc}</p>", status_code=502)

    # Om Hydra redan minns sessionen — godkänn automatiskt.
    if info.get("skip"):
        redirect = _hydra_accept(
            "/admin/oauth2/auth/requests/login/accept",
            "login_challenge", login_challenge,
            {"subject": info["subject"]},
        )
        return RedirectResponse(redirect, status_code=303)

    t, locale = _t_for_request(request)
    return templates.TemplateResponse(
        request, "login.html",
        {"challenge": login_challenge, "error": "", "t": t, "locale": locale},
    )


@app.post("/login", response_class=HTMLResponse)
async def login_post(
    request: Request,
    login_challenge: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
):
    t, locale = _t_for_request(request)
    if username not in ALLOWED_USERS or not _verify_password(username, password):
        return templates.TemplateResponse(
            request, "login.html",
            {"challenge": login_challenge, "error": t("login_error_credentials"), "t": t, "locale": locale},
            status_code=401,
        )

    try:
        redirect = _hydra_accept(
            "/admin/oauth2/auth/requests/login/accept",
            "login_challenge", login_challenge,
            {
                "subject": username,
                "remember": True,
                "remember_for": 86400 * 30,  # 30 dagar
            },
        )
    except Exception as exc:
        return HTMLResponse(f"<p>Hydra-fel: {exc}</p>", status_code=502)

    return RedirectResponse(redirect, status_code=303)


# ------------------------------------------------------------------
# Consent — auto-godkänn för ägare (single-user setup)
# ------------------------------------------------------------------


@app.get("/consent")
async def consent_get(consent_challenge: str = ""):
    if not consent_challenge:
        return HTMLResponse("<p>Ogiltig förfrågan (consent_challenge saknas).</p>", status_code=400)

    try:
        info = _hydra_get(
            "/admin/oauth2/auth/requests/consent",
            "consent_challenge", consent_challenge,
        )
    except Exception as exc:
        return HTMLResponse(f"<p>Hydra-fel: {exc}</p>", status_code=502)

    requested_scope = info.get("requested_scope", [])

    # Hydra v2.2 doesn't map the `resource` param to requested_access_token_audience
    # automatically, so we parse it from request_url and grant it explicitly.
    # Include both trailing-slash variants so the JWT aud matches regardless of
    # whether claude.ai compares against the connector URL (no slash) or the
    # RFC 8707 resource indicator it sends (with slash).
    from urllib.parse import parse_qs, urlparse as _urlparse
    _rurl = info.get("request_url", "")
    _resource = parse_qs(_urlparse(_rurl).query).get("resource", [])
    _resource_both = []
    for r in _resource:
        _resource_both.append(r)
        _resource_both.append(r.rstrip("/") if r.endswith("/") else r + "/")
    audience = list(set(_resource_both) | set(info.get("requested_access_token_audience") or []))

    redirect = _hydra_accept(
        "/admin/oauth2/auth/requests/consent/accept",
        "consent_challenge", consent_challenge,
        {
            "grant_scope": requested_scope,
            "grant_access_token_audience": audience,
            "remember": True,
            "remember_for": 86400 * 30,
            "session": {
                "id_token": {
                    "email": f"{info.get('subject', 'alice')}@personal.example.com",
                    "name": info.get("subject", "alice"),
                }
            },
        },
    )
    return RedirectResponse(redirect, status_code=303)


# ------------------------------------------------------------------
# Health
# ------------------------------------------------------------------


@app.get("/health")
async def health():
    return {"status": "ok", "service": "memaix-login"}
