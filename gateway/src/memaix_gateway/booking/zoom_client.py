# SPDX-License-Identifier: AGPL-3.0-or-later
"""Zoom Server-to-Server OAuth client — memaix-src card 85854d2c.

App-level credentials (account_id/client_id/client_secret), not a per-host
interactive consent flow — one Zoom app backs every host on this
deployment, per Jimmy's decision recorded on the card. This mirrors the
CalDAV/email secrets convention (config.secret(ref)), not the per-user
OAuth token store used for Google Calendar (tools/account.py) — Zoom
credentials belong to the deployment, not to an individual host.

CAVEAT: the exact request/response shape below (param names, endpoint
path, required scope) is written from Zoom's published Server-to-Server
OAuth guide but was NOT confirmed against a live call — Zoom's interactive
API reference is a JS-rendered SPA that couldn't be scraped during prior
research. Verify every shape here against a real Zoom account before
relying on it in production; don't extend this module by guessing further
shapes the same way.
"""

from __future__ import annotations

_TOKEN_URL = "https://zoom.us/oauth/token"  # nosec B105 -- a URL, not a credential
_API_BASE = "https://api.zoom.us/v2"


class ZoomAuthError(Exception):
    """Raised when the Server-to-Server OAuth token request fails."""


class ZoomAPIError(Exception):
    """Raised when a Zoom API call fails after a token was obtained."""


def get_access_token(account_id: str, client_id: str, client_secret: str) -> str:
    """POST grant_type=account_credentials to Zoom's token endpoint.
    Returns a bearer token valid for ~1 hour — callers should not cache
    this across requests without also tracking expiry; a fresh token is
    fetched per meeting-creation call for simplicity, same tradeoff as
    e.g. calendar.py's per-call adapters (no shared token cache) rather
    than optimizing before there's a proven need."""
    import requests

    r = requests.post(
        _TOKEN_URL,
        params={"grant_type": "account_credentials", "account_id": account_id},
        auth=(client_id, client_secret),
        timeout=10,
    )
    if r.status_code != 200:
        raise ZoomAuthError(f"Zoom token request failed: {r.status_code} {r.text}")
    data = r.json()
    token = data.get("access_token")
    if not token:
        raise ZoomAuthError(f"Zoom token response had no access_token: {data!r}")
    return token


def create_zoom_meeting(access_token: str, *, topic: str, start_time: str, duration_min: int) -> dict:
    """Create a scheduled Zoom meeting on the app's own user (users/me),
    per Server-to-Server OAuth's normal usage where the app itself owns a
    licensed user. Returns Zoom's raw meeting object; callers should read
    at least "join_url" and "id" (needed later for update/delete)."""
    import requests

    r = requests.post(
        f"{_API_BASE}/users/me/meetings",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "topic": topic,
            "type": 2,  # scheduled meeting
            "start_time": start_time,
            "duration": duration_min,
        },
        timeout=10,
    )
    if r.status_code not in (200, 201):
        raise ZoomAPIError(f"Zoom meeting creation failed: {r.status_code} {r.text}")
    return r.json()


def update_zoom_meeting(access_token: str, meeting_id: str, *, start_time: str, duration_min: int) -> None:
    """PATCH a Zoom meeting's time — used on booking reschedule. The
    meeting's join_url does not change."""
    import requests

    r = requests.patch(
        f"{_API_BASE}/meetings/{meeting_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"start_time": start_time, "duration": duration_min},
        timeout=10,
    )
    if r.status_code not in (200, 204):
        raise ZoomAPIError(f"Zoom meeting update failed: {r.status_code} {r.text}")


def delete_zoom_meeting(access_token: str, meeting_id: str) -> None:
    """DELETE a Zoom meeting — used on booking cancel to avoid leaving an
    orphaned meeting around (Zoom meetings do expire on their own after
    their scheduled time, so this is cleanliness, not correctness)."""
    import requests

    r = requests.delete(
        f"{_API_BASE}/meetings/{meeting_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    if r.status_code not in (200, 204, 404):
        raise ZoomAPIError(f"Zoom meeting deletion failed: {r.status_code} {r.text}")
