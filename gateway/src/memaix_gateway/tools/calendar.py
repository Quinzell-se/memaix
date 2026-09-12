# SPDX-License-Identifier: AGPL-3.0-or-later
"""calendar_* tools — CalDAV or Google Calendar REST with injected client for testability.

The _dav keyword argument accepts a duck-typed object.  When None,
a real caldav.DAVClient connection is created from project config.

_dav duck type (must implement):
  list_events(start: datetime, end: datetime) -> list[dict]
    where dict has at minimum: id, title, start, end
  create_event(uid, title, start, end, attendees, location, description) -> dict
  update_event(id, **fields) -> dict
  delete_event(id) -> None
  find_events(start: datetime, end: datetime) -> list[dict]  (same as list_events)

For real CalDAV the adapter is inline below (_RealDavAdapter).

Outbox gate:
  calendar_create/calendar_update are routed through the approval outbox (see
  outbox/policy.py) exactly like email_send — when action_mode() resolves to
  'review', the call is queued and returns {"pending": True, "action_id": ...}
  instead of touching the calendar. _confirmed=True (used by outbox.execute
  after approval) always executes immediately.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from .. import config
from ..acl import Acl


class CalendarAuthRequired(Exception):
    """Raised when the user has no linked calendar account for this project."""

    def __init__(self, link_url: str, options: list[dict] | None = None) -> None:
        self.link_url = link_url
        self.options = options or []
        super().__init__("auth_required: configure calendar via calendar_setup")


# ------------------------------------------------------------------
# Per-user Google Calendar REST adapter
# ------------------------------------------------------------------


class _PerUserGoogleAdapter:
    """Google Calendar REST API v3 using a per-user OAuth access token."""

    _BASE = "https://www.googleapis.com/calendar/v3"

    def __init__(self, access_token: str) -> None:
        self._token = access_token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}

    def _get(self, path: str, **params) -> dict:
        import requests
        r = requests.get(f"{self._BASE}{path}", headers=self._headers(), params=params, timeout=10)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, body: dict, **params) -> dict:
        import requests
        r = requests.post(f"{self._BASE}{path}", headers=self._headers(), json=body, params=params, timeout=10)
        r.raise_for_status()
        return r.json()

    def _patch(self, path: str, body: dict) -> dict:
        import requests
        r = requests.patch(f"{self._BASE}{path}", headers=self._headers(), json=body, timeout=10)
        r.raise_for_status()
        return r.json()

    def _delete(self, path: str) -> None:
        import requests
        r = requests.delete(f"{self._BASE}{path}", headers=self._headers(), timeout=10)
        r.raise_for_status()

    @staticmethod
    def _to_dict(item: dict) -> dict:
        start = item.get("start", {})
        end = item.get("end", {})
        # originalStartTime is present on an expanded singleEvents=true
        # instance iff Google materialized a distinct event object for it —
        # i.e. it was individually modified (title, attendees, time, ...).
        # A clean occurrence of a series never has this key at all. Do NOT
        # compare against start: an exception whose *time* is unchanged
        # (e.g. only its title changed) would otherwise be misclassified as
        # a normal occurrence and wrongly inherit a series override.
        is_exception = bool(item.get("originalStartTime"))
        return {
            "id": item.get("id", ""),
            "title": item.get("summary", ""),
            "start": start.get("dateTime") or start.get("date", ""),
            "end": end.get("dateTime") or end.get("date", ""),
            "location": item.get("location", ""),
            "description": item.get("description", ""),
            # memaix-src card c7698ff3 — series identity for per-event overrides.
            # singleEvents=true (list_events below) expands recurrences and
            # populates recurringEventId on each instance of a series.
            "series_id": item.get("recurringEventId"),
            "is_exception": is_exception,
            # Google: transparency:"transparent" == Free, default "opaque" == Busy.
            "source_busy": item.get("transparency", "opaque") != "transparent",
            # memaix-src card 85854d2c — set only on a create_event(want_conference=True)
            # response; entryPointType "video" is the Meet join link, Google also
            # returns "more" entry poi