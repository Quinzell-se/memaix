# SPDX-License-Identifier: AGPL-3.0-or-later
"""calendar_* tools — CalDAV with injected client for testability.

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
"""

from __future__ import annotations

from datetime import datetime, timedelta

from .. import config
from ..acl import Acl


# ------------------------------------------------------------------
# Real CalDAV adapter (wraps caldav library)
# ------------------------------------------------------------------


class _RealDavAdapter:
    def __init__(self, acl: Acl, project: str) -> None:
        import caldav

        cfg = acl.resource(project, "calendar")
        if not cfg:
            raise ValueError(f"project {project!r} has no calendar configured")
        password = config.secret(cfg.get("password_ref"))
        client = caldav.DAVClient(
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
) -> dict:
    """Create an event.  Returns {id, title, start, end}."""
    acl.enforce(user_id, project, "collaborator")
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
    **fields,
) -> dict:
    """Update event fields.  Returns updated event dict."""
    acl.enforce(user_id, project, "collaborator")
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
