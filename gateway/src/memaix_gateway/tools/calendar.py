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

    def _post(self, path: str, body: dict) -> dict:
        import requests
        r = requests.post(f"{self._BASE}{path}", headers=self._headers(), json=body, timeout=10)
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
        return {
            "id": item.get("id", ""),
            "title": item.get("summary", ""),
            "start": start.get("dateTime") or start.get("date", ""),
            "end": end.get("dateTime") or end.get("date", ""),
            "location": item.get("location", ""),
            "description": item.get("description", ""),
        }

    def list_events(self, start: datetime, end: datetime) -> list[dict]:
        data = self._get(
            "/calendars/primary/events",
            timeMin=start.isoformat() if start.tzinfo else start.isoformat() + "Z",
            timeMax=end.isoformat() if end.tzinfo else end.isoformat() + "Z",
            singleEvents="true",
            orderBy="startTime",
        )
        return [self._to_dict(e) for e in data.get("items", [])]

    find_events = list_events

    def create_event(
        self,
        uid: str,
        title: str,
        start: datetime,
        end: datetime,
        attendees: list[str] | None = None,
        location: str | None = None,
        description: str | None = None,
    ) -> dict:
        body: dict = {
            "summary": title,
            "start": {"dateTime": start.isoformat(), "timeZone": "UTC"},
            "end": {"dateTime": end.isoformat(), "timeZone": "UTC"},
        }
        if location:
            body["location"] = location
        if description:
            body["description"] = description
        if attendees:
            body["attendees"] = [{"email": a} for a in attendees]
        return self._to_dict(self._post("/calendars/primary/events", body))

    def update_event(self, id: str, **fields) -> dict:
        body: dict = {}
        if "title" in fields:
            body["summary"] = fields["title"]
        if "location" in fields:
            body["location"] = fields["location"]
        if "description" in fields:
            body["description"] = fields["description"]
        if "start" in fields:
            body["start"] = {"dateTime": fields["start"], "timeZone": "UTC"}
        if "end" in fields:
            body["end"] = {"dateTime": fields["end"], "timeZone": "UTC"}
        return self._to_dict(self._patch(f"/calendars/primary/events/{id}", body))

    def delete_event(self, id: str) -> None:
        self._delete(f"/calendars/primary/events/{id}")


# ------------------------------------------------------------------
# iCal secret-URL adapter (read-only)
# ------------------------------------------------------------------


class _ICalAdapter:
    """Fetches a secret iCal URL and returns events in the time range."""

    def __init__(self, ical_url: str) -> None:
        self._url = ical_url

    def _fetch(self) -> list[dict]:
        from datetime import date, timezone

        import requests
        import vobject

        from ..safety.net import validate_external_url

        validate_external_url(self._url)  # authoritative SSRF check before fetching the secret iCal URL
        r = requests.get(self._url, timeout=10)
        r.raise_for_status()
        cal = vobject.readOne(r.text)
        events: list[dict] = []
        for component in cal.components():
            if component.name != "VEVENT":
                continue
            dtstart = component.dtstart.value
            dtend = getattr(component, "dtend", None)
            dtend = dtend.value if dtend else dtstart

            # Normalize date → datetime
            if isinstance(dtstart, date) and not isinstance(dtstart, datetime):
                dtstart = datetime(dtstart.year, dtstart.month, dtstart.day, tzinfo=timezone.utc)
            if isinstance(dtend, date) and not isinstance(dtend, datetime):
                dtend = datetime(dtend.year, dtend.month, dtend.day, tzinfo=timezone.utc)

            events.append({
                "id": str(getattr(component, "uid", "")).strip() or f"ical-{len(events)}",
                "title": str(getattr(component, "summary", "")).strip(),
                "start": dtstart.isoformat() if isinstance(dtstart, datetime) else str(dtstart),
                "end": dtend.isoformat() if isinstance(dtend, datetime) else str(dtend),
                "location": str(getattr(component, "location", "")).strip(),
                "description": str(getattr(component, "description", "")).strip(),
                "_dtstart": dtstart,
                "_dtend": dtend,
            })
        return events

    def _in_range(self, event: dict, start: datetime, end: datetime) -> bool:
        from datetime import timezone
        def _tz(dt: datetime) -> datetime:
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        ev_start = _tz(event["_dtstart"]) if isinstance(event["_dtstart"], datetime) else _tz(start)
        ev_end = _tz(event["_dtend"]) if isinstance(event["_dtend"], datetime) else _tz(end)
        s = _tz(start)
        e = _tz(end)
        return ev_start < e and ev_end > s

    def list_events(self, start: datetime, end: datetime) -> list[dict]:
        raw = self._fetch()
        filtered = [e for e in raw if self._in_range(e, start, end)]
        # Strip internal keys before returning
        return [{k: v for k, v in e.items() if not k.startswith("_")} for e in filtered]

    find_events = list_events

    def create_event(self, *args, **kwargs):
        raise NotImplementedError("iCal feed is read-only — use calendar_setup mode=oauth for write access")

    def update_event(self, *args, **kwargs):
        raise NotImplementedError("iCal feed is read-only — use calendar_setup mode=oauth for write access")

    def delete_event(self, *args, **kwargs):
        raise NotImplementedError("iCal feed is read-only — use calendar_setup mode=oauth for write access")


# ------------------------------------------------------------------
# Google FreeBusy adapter (read-only, no event titles)
# ------------------------------------------------------------------


class _FreeBusyAdapter:
    """Queries Google FreeBusy API — returns only busy blocks, no event details."""

    _ENDPOINT = "https://www.googleapis.com/calendar/v3/freeBusy"

    def __init__(self, calendar_id: str, api_key: str) -> None:
        self._calendar_id = calendar_id
        self._api_key = api_key

    def list_events(self, start: datetime, end: datetime) -> list[dict]:
        from datetime import timezone

        import requests

        def _iso(dt: datetime) -> str:
            if not dt.tzinfo:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()

        r = requests.post(
            self._ENDPOINT,
            params={"key": self._api_key},
            json={
                "timeMin": _iso(start),
                "timeMax": _iso(end),
                "items": [{"id": self._calendar_id}],
            },
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        busy = data.get("calendars", {}).get(self._calendar_id, {}).get("busy", [])
        return [
            {"id": f"busy-{i}", "title": "Busy", "start": b["start"], "end": b["end"], "location": "", "description": ""}
            for i, b in enumerate(busy)
        ]

    find_events = list_events

    def create_event(self, *args, **kwargs):
        raise NotImplementedError("FreeBusy mode is read-only — use calendar_setup mode=oauth for write access")

    def update_event(self, *args, **kwargs):
        raise NotImplementedError("FreeBusy mode is read-only — use calendar_setup mode=oauth for write access")

    def delete_event(self, *args, **kwargs):
        raise NotImplementedError("FreeBusy mode is read-only — use calendar_setup mode=oauth for write access")


# ------------------------------------------------------------------
# Real CalDAV adapter (wraps caldav library)
# ------------------------------------------------------------------


class _RealDavAdapter:
    def __init__(self, acl: Acl, project: str) -> None:
        # caldav's package __init__ exposes DAVClient via a lazy PEP 562
        # __getattr__ typed to return `object`, which makes mypy treat
        # `caldav.DAVClient(...)` as calling a non-callable. Importing the
        # real class from its submodule keeps the actual type.
        from caldav.davclient import DAVClient

        cfg = acl.resource(project, "calendar")
        if not cfg:
            raise ValueError(f"project {project!r} has no calendar configured")
        password = config.secret(cfg.get("password_ref"))
        client = DAVClient(
            url=cfg["url"],
            username=cfg.get("user", ""),
            password=password,
        )
        principal = client.principal()
        cals = principal.calendars()
        if not cals:
            raise RuntimeError("no calendars found for project")
        self._cal = cals[0]

    def _vevent(self, event):
        return event.vobject_instance.vevent

    def _event_to_dict(self, event) -> dict:
        ve = self._vevent(event)
        return {
            "id": str(ve.uid.value),
            "title": str(ve.summary.value) if hasattr(ve, "summary") else "",
            "start": str(ve.dtstart.value),
            "end": str(ve.dtend.value) if hasattr(ve, "dtend") else "",
            "location": str(ve.location.value) if hasattr(ve, "location") else "",
            "description": str(ve.description.value) if hasattr(ve, "description") else "",
        }

    def list_events(self, start: datetime, end: datetime) -> list[dict]:
        events = self._cal.date_search(start=start, end=end, expand=True)
        return [self._event_to_dict(e) for e in events]

    find_events = list_events

    def create_event(
        self,
        uid: str,
        title: str,
        start: datetime,
        end: datetime,
        attendees: list[str] | None = None,
        location: str | None = None,
        description: str | None = None,
    ) -> dict:
        import vobject

        cal = vobject.iCalendar()
        event = cal.add("vevent")
        event.add("uid").value = uid
        event.add("summary").value = title
        event.add("dtstart").value = start
        event.add("dtend").value = end
        if location:
            event.add("location").value = location
        if description:
            event.add("description").value = description
        if attendees:
            for att in attendees:
                event.add("attendee").value = att
        self._cal.save_event(cal.serialize())
        return {"id": uid, "title": title, "start": str(start), "end": str(end)}

    def update_event(self, id: str, **fields) -> dict:
        events = self._cal.search(uid=id)
        if not events:
            raise FileNotFoundError(f"event not found: {id!r}")
        event = events[0]
        ve = self._vevent(event)
        if "title" in fields:
            ve.summary.value = fields["title"]
        if "location" in fields and hasattr(ve, "location"):
            ve.location.value = fields["location"]
        if "description" in fields and hasattr(ve, "description"):
            ve.description.value = fields["description"]
        if "start" in fields:
            ve.dtstart.value = datetime.fromisoformat(fields["start"])
        if "end" in fields:
            ve.dtend.value = datetime.fromisoformat(fields["end"])
        event.save()
        return self._event_to_dict(event)

    def delete_event(self, id: str) -> None:
        events = self._cal.search(uid=id)
        if not events:
            raise FileNotFoundError(f"event not found: {id!r}")
        events[0].delete()


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _get_dav(acl: Acl, project: str, _dav) -> _RealDavAdapter:
    if _dav is not None:
        return _dav
    return _RealDavAdapter(acl, project)


def _parse_dt(s: str) -> datetime:
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"invalid ISO 8601 datetime: {s!r}") from exc


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


def calendar_list(
    acl: Acl,
    user_id: str,
    project: str,
    start: str,
    end: str,
    *,
    _dav=None,
) -> list[dict]:
    """List events in [start, end].  Returns [{id, title, start, end, ...}]."""
    acl.enforce(user_id, project, "collaborator")
    start_dt = _parse_dt(start)
    end_dt = _parse_dt(end)
    dav = _get_dav(acl, project, _dav)
    return dav.list_events(start_dt, end_dt)


def calendar_find_free(
    acl: Acl,
    user_id: str,
    project: str,
    duration_min: int,
    within_start: str,
    within_end: str,
    *,
    _dav=None,
) -> list[dict]:
    """Find free slots of *duration_min* minutes within [within_start, within_end].

    Returns [{start, end}] for each free block (minimum duration).
    """
    acl.enforce(user_id, project, "collaborator")
    ws = _parse_dt(within_start)
    we = _parse_dt(within_end)
    duration = timedelta(minutes=duration_min)
    dav = _get_dav(acl, project, _dav)

    busy = sorted(dav.find_events(ws, we), key=lambda e: e["start"])

    # Build free slots
    free: list[dict] = []
    cursor = ws
    for ev in busy:
        ev_start = _parse_dt(ev["start"]) if isinstance(ev["start"], str) else ev["start"]
        ev_end = _parse_dt(ev["end"]) if isinstance(ev["end"], str) else ev["end"]
        if ev_start > cursor + duration:
            free.append({"start": cursor.isoformat(), "end": ev_start.isoformat()})
        if ev_end > cursor:
            cursor = ev_end
    if we > cursor + duration:
        free.append({"start": cursor.isoformat(), "end": we.isoformat()})
    return free


def _maybe_queue(acl, user_id: str, project: str, tool: str, args: dict, *, _outbox, _cfg) -> dict | None:
    """Return a {"pending": ...} dict if this action should be queued, else None."""
    from ..outbox.policy import action_mode
    from ..outbox.preview import render_preview
    from ..outbox.queue import default_queue

    memaix_cfg = _cfg if _cfg is not None else config.load()
    if action_mode(memaix_cfg, acl, project, tool, args) != "review":
        return None
    queue = _outbox if _outbox is not None else default_queue()
    action_id = queue.enqueue(user_id, project, tool, args, render_preview(tool, args))
    return {"pending": True, "action_id": action_id, "note": "Väntar på godkännande i utkorgen"}


def calendar_create(
    acl: Acl,
    user_id: str,
    project: str,
    title: str,
    start: str,
    end: str,
    attendees: list[str] | None = None,
    location: str | None = None,
    description: str | None = None,
    *,
    _dav=None,
    _confirmed: bool = False,
    _outbox=None,
    _cfg: dict | None = None,
) -> dict:
    """Create an event.  Returns {id, title, start, end}.

    Queued for approval instead of created when the outbox policy resolves
    to 'review' (see module docstring) — unless _confirmed=True.
    """
    acl.enforce(user_id, project, "collaborator")
    if not _confirmed:
        args = {
            "title": title, "start": start, "end": end, "attendees": attendees,
            "location": location, "description": description,
        }
        queued = _maybe_queue(acl, user_id, project, "calendar_create", args, _outbox=_outbox, _cfg=_cfg)
        if queued is not None:
            return queued

    start_dt = _parse_dt(start)
    end_dt = _parse_dt(end)
    import uuid as _uuid

    uid = _uuid.uuid4().hex
    dav = _get_dav(acl, project, _dav)
    return dav.create_event(uid, title, start_dt, end_dt, attendees, location, description)


def calendar_update(
    acl: Acl,
    user_id: str,
    project: str,
    id: str,
    *,
    _dav=None,
    _confirmed: bool = False,
    _outbox=None,
    _cfg: dict | None = None,
    **fields,
) -> dict:
    """Update event fields.  Returns updated event dict.

    Queued for approval instead of applied when the outbox policy resolves
    to 'review' (see module docstring) — unless _confirmed=True.
    """
    acl.enforce(user_id, project, "collaborator")
    if not _confirmed:
        args = {"id": id, **fields}
        queued = _maybe_queue(acl, user_id, project, "calendar_update", args, _outbox=_outbox, _cfg=_cfg)
        if queued is not None:
            return queued

    dav = _get_dav(acl, project, _dav)
    return dav.update_event(id, **fields)


def calendar_delete(
    acl: Acl,
    user_id: str,
    project: str,
    id: str,
    *,
    _dav=None,
) -> dict:
    """Delete an event.  Always returns requires_confirmation=True (SAFETY.md §8)."""
    acl.enforce(user_id, project, "collaborator")
    dav = _get_dav(acl, project, _dav)
    dav.delete_event(id)
    return {"deleted": True, "requires_confirmation": True}
