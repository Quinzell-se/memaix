# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for calendar_* tools.

All CalDAV calls are replaced by an in-process mock — no network required.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from memaix_gateway.acl import Acl, AccessDenied
from memaix_gateway.tools.calendar import (
    calendar_create,
    calendar_delete,
    calendar_find_free,
    calendar_list,
    calendar_update,
)


# ------------------------------------------------------------------
# Mock CalDAV adapter
# ------------------------------------------------------------------


class _MockDav:
    """Duck-type for _RealDavAdapter / caldav objects used by calendar_* tools."""

    def __init__(self, events: list[dict] | None = None) -> None:
        self._events: list[dict] = list(events or [])

    def list_events(self, start: datetime, end: datetime) -> list[dict]:
        return [
            e
            for e in self._events
            if _parse(e["start"]) >= start and _parse(e["end"]) <= end
        ]

    find_events = list_events

    def create_event(
        self,
        uid: str,
        title: str,
        start: datetime,
        end: datetime,
        attendees=None,
        location=None,
        description=None,
    ) -> dict:
        ev = {
            "id": uid,
            "title": title,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "location": location or "",
            "description": description or "",
        }
        self._events.append(ev)
        return ev

    def update_event(self, id: str, **fields) -> dict:
        for ev in self._events:
            if ev["id"] == id:
                ev.update(fields)
                return ev
        raise FileNotFoundError(f"event not found: {id!r}")

    def delete_event(self, id: str) -> None:
        before = len(self._events)
        self._events = [e for e in self._events if e["id"] != id]
        if len(self._events) == before:
            raise FileNotFoundError(f"event not found: {id!r}")


def _parse(s) -> datetime:
    if isinstance(s, datetime):
        return s
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture()
def acl():
    return Acl(
        users={
            "alice": {"grants": {"proj": "owner"}},
            "carol": {"grants": {"proj": "collaborator"}},
            "bob": {"grants": {"proj": "reader"}},
        },
        projects={
            "proj": {
                "calendar": {
                    "url": "https://cal.example.com/dav/",
                    "user": "alice",
                    "password_ref": "env:FAKE_CAL_PASSWORD",
                }
            }
        },
    )


@pytest.fixture()
def dav():
    return _MockDav(
        [
            {
                "id": "ev-001",
                "title": "Standup",
                "start": "2024-06-03T09:00:00+00:00",
                "end": "2024-06-03T09:30:00+00:00",
            },
            {
                "id": "ev-002",
                "title": "Lunch",
                "start": "2024-06-03T12:00:00+00:00",
                "end": "2024-06-03T13:00:00+00:00",
            },
        ]
    )


# ------------------------------------------------------------------
# ACL enforcement
# ------------------------------------------------------------------


def test_calendar_list_denied_for_reader(acl, dav):
    with pytest.raises(AccessDenied):
        calendar_list(acl, "bob", "proj", "2024-06-03T00:00:00", "2024-06-03T23:59:59", _dav=dav)


def test_calendar_create_denied_for_reader(acl, dav):
    with pytest.raises(AccessDenied):
        calendar_create(
            acl, "bob", "proj", "Meeting", "2024-06-04T10:00:00", "2024-06-04T11:00:00", _dav=dav
        )


def test_calendar_list_denied_for_unknown_user(acl, dav):
    with pytest.raises(AccessDenied):
        calendar_list(acl, "ghost", "proj", "2024-06-03T00:00:00", "2024-06-03T23:59:59", _dav=dav)


# ------------------------------------------------------------------
# calendar_list
# ------------------------------------------------------------------


def test_calendar_list_returns_events(acl, dav):
    results = calendar_list(
        acl, "carol", "proj",
        "2024-06-03T00:00:00+00:00",
        "2024-06-03T23:59:59+00:00",
        _dav=dav,
    )
    assert len(results) == 2
    titles = [e["title"] for e in results]
    assert "Standup" in titles
    assert "Lunch" in titles


def test_calendar_list_correct_fields(acl, dav):
    results = calendar_list(
        acl, "carol", "proj",
        "2024-06-03T00:00:00+00:00",
        "2024-06-03T23:59:59+00:00",
        _dav=dav,
    )
    ev = results[0]
    assert "id" in ev
    assert "title" in ev
    assert "start" in ev
    assert "end" in ev


# ------------------------------------------------------------------
# calendar_create
# ------------------------------------------------------------------


def test_calendar_create_returns_id(acl, dav):
    result = calendar_create(
        acl, "carol", "proj",
        "New Meeting",
        "2024-06-05T14:00:00+00:00",
        "2024-06-05T15:00:00+00:00",
        _dav=dav,
    )
    assert "id" in result
    assert result["title"] == "New Meeting"


def test_calendar_create_stores_event(acl, dav):
    calendar_create(
        acl, "carol", "proj",
        "Workshop",
        "2024-06-05T10:00:00+00:00",
        "2024-06-05T12:00:00+00:00",
        _dav=dav,
    )
    results = calendar_list(
        acl, "carol", "proj",
        "2024-06-05T00:00:00+00:00",
        "2024-06-05T23:59:59+00:00",
        _dav=dav,
    )
    assert any(e["title"] == "Workshop" for e in results)


# ------------------------------------------------------------------
# calendar_delete
# ------------------------------------------------------------------


def test_calendar_delete_returns_requires_confirmation(acl, dav):
    result = calendar_delete(acl, "carol", "proj", "ev-001", _dav=dav)
    assert result["deleted"] is True
    assert result["requires_confirmation"] is True


def test_calendar_delete_removes_event(acl, dav):
    calendar_delete(acl, "carol", "proj", "ev-001", _dav=dav)
    results = calendar_list(
        acl, "carol", "proj",
        "2024-06-03T00:00:00+00:00",
        "2024-06-03T23:59:59+00:00",
        _dav=dav,
    )
    assert not any(e["id"] == "ev-001" for e in results)


def test_calendar_delete_missing_raises(acl, dav):
    with pytest.raises(FileNotFoundError):
        calendar_delete(acl, "carol", "proj", "nonexistent", _dav=dav)


# ------------------------------------------------------------------
# calendar_find_free
# ------------------------------------------------------------------


def test_calendar_find_free_returns_slots(acl, dav):
    # Range: 08:00–18:00, two busy slots: 09:00–09:30, 12:00–13:00
    slots = calendar_find_free(
        acl, "carol", "proj",
        duration_min=30,
        within_start="2024-06-03T08:00:00+00:00",
        within_end="2024-06-03T18:00:00+00:00",
        _dav=dav,
    )
    assert isinstance(slots, list)
    assert len(slots) >= 1
    for s in slots:
        assert "start" in s
        assert "end" in s


# ------------------------------------------------------------------
# Validation
# ------------------------------------------------------------------


def test_invalid_datetime_format_raises(acl, dav):
    with pytest.raises((ValueError, Exception)):
        calendar_list(acl, "carol", "proj", "not-a-date", "also-not", _dav=dav)


def test_calendar_update_modifies_event(acl, dav):
    result = calendar_update(acl, "carol", "proj", "ev-001", _dav=dav, title="Updated Standup")
    assert result["title"] == "Updated Standup"


# ------------------------------------------------------------------
# Outbox gate (FEATURE-APPROVAL-OUTBOX.md)
# ------------------------------------------------------------------


class _FakeOutbox:
    def __init__(self) -> None:
        self.enqueued: list = []

    def enqueue(self, user, project, tool, args, preview, ttl_h=72):
        self.enqueued.append((user, project, tool, args, preview))
        return "fake-action-id"


def test_calendar_create_review_mode_queues_instead_of_creating(acl, dav):
    outbox = _FakeOutbox()
    cfg = {"memaix": {"outbox": {"default_mode": "review"}}}
    before = len(dav._events)
    result = calendar_create(
        acl, "carol", "proj", "Planning", "2024-06-05T10:00:00", "2024-06-05T11:00:00",
        _dav=dav, _outbox=outbox, _cfg=cfg,
    )
    assert result["pending"] is True
    assert result["action_id"] == "fake-action-id"
    assert len(dav._events) == before  # nothing was actually created
    assert outbox.enqueued[0][2] == "calendar_create"


def test_calendar_create_confirmed_bypasses_outbox(acl, dav):
    outbox = _FakeOutbox()
    cfg = {"memaix": {"outbox": {"default_mode": "review"}}}
    result = calendar_create(
        acl, "carol", "proj", "Planning", "2024-06-05T10:00:00", "2024-06-05T11:00:00",
        _dav=dav, _outbox=outbox, _cfg=cfg, _confirmed=True,
    )
    assert "id" in result
    assert outbox.enqueued == []


def test_calendar_update_review_mode_queues_instead_of_updating(acl, dav):
    outbox = _FakeOutbox()
    cfg = {"memaix": {"outbox": {"default_mode": "review"}}}
    result = calendar_update(
        acl, "carol", "proj", "ev-001", _dav=dav, _outbox=outbox, _cfg=cfg, title="New title"
    )
    assert result["pending"] is True
    # The event itself is untouched.
    assert dav._events[0]["title"] == "Standup"
    assert outbox.enqueued[0][2] == "calendar_update"


def test_calendar_update_confirmed_bypasses_outbox(acl, dav):
    outbox = _FakeOutbox()
    cfg = {"memaix": {"outbox": {"default_mode": "review"}}}
    result = calendar_update(
        acl, "carol", "proj", "ev-001", _dav=dav, _outbox=outbox, _cfg=cfg,
        _confirmed=True, title="New title",
    )
    assert result["title"] == "New title"
    assert outbox.enqueued == []


def test_calendar_create_still_enforces_role_before_queueing(acl, dav):
    outbox = _FakeOutbox()
    cfg = {"memaix": {"outbox": {"default_mode": "review"}}}
    with pytest.raises(AccessDenied):
        calendar_create(
            acl, "bob", "proj", "Meeting", "2024-06-05T10:00:00", "2024-06-05T11:00:00",
            _dav=dav, _outbox=outbox, _cfg=cfg,
        )
    assert outbox.enqueued == []


def test_allowlist_forces_review_even_in_auto_mode(acl, dav):
    acl.projects["proj"]["allowlist"] = ["@trusted.example"]
    outbox = _FakeOutbox()
    result = calendar_create(
        acl, "carol", "proj", "Ext meeting", "2024-06-05T10:00:00", "2024-06-05T11:00:00",
        attendees=["someone@evil.example"], _dav=dav, _outbox=outbox,
    )
    assert result["pending"] is True
