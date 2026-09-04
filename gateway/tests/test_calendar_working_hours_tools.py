# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for tools.calendar.calendar_working_hours_get/set and their effect
on calendar_find_free — memaix-src card e21fde31."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from memaix_gateway.acl import Acl, AccessDenied
from memaix_gateway.tools.calendar import (
    calendar_find_free,
    calendar_working_hours_get,
    calendar_working_hours_set,
)


def _parse(s: str) -> datetime:
    return datetime.fromisoformat(s)


class _MockDav:
    def __init__(self, events=None) -> None:
        self._events = list(events or [])

    def list_events(self, start, end):
        return [e for e in self._events if _parse(e["start"]) >= start and _parse(e["end"]) <= end]

    find_events = list_events


@pytest.fixture()
def acl(tmp_path):
    return Acl(
        users={
            "alice": {"grants": {"proj": "owner"}},
            "carol": {"grants": {"proj": "collaborator"}},
            "bob": {"grants": {"proj": "reader"}},
        },
        projects={
            "proj": {
                "vault": str(tmp_path),
                "calendar": {"url": "https://cal.example.com/dav/", "user": "alice", "password_ref": "env:X"},
            }
        },
    )


def test_calendar_working_hours_get_denied_without_grant(acl):
    with pytest.raises(AccessDenied):
        calendar_working_hours_get(acl, "eve", "proj")


def test_calendar_working_hours_get_empty_when_never_set(acl):
    assert calendar_working_hours_get(acl, "bob", "proj") == {}


def test_calendar_working_hours_set_denied_for_reader(acl):
    with pytest.raises(AccessDenied):
        calendar_working_hours_set(acl, "bob", "proj", "Europe/Stockholm", {})


def test_calendar_working_hours_set_then_get_roundtrips(acl):
    week = {"mon": [{"start": "09:00", "end": "17:00"}]}
    result = calendar_working_hours_set(acl, "carol", "proj", "Europe/Stockholm", week)
    assert result == {"ok": True, "tz": "Europe/Stockholm", "week": week}
    assert calendar_working_hours_get(acl, "carol", "proj") == {"tz": "Europe/Stockholm", "week": week}


def test_calendar_working_hours_set_rejects_unknown_timezone(acl):
    result = calendar_working_hours_set(acl, "carol", "proj", "Not/AZone", {})
    assert result["ok"] is False


def test_calendar_working_hours_set_rejects_invalid_week(acl):
    result = calendar_working_hours_set(
        acl, "carol", "proj", "Europe/Stockholm", {"mon": [{"start": "17:00", "end": "09:00"}]}
    )
    assert result["ok"] is False


def test_calendar_find_free_narrows_to_working_hours(acl):
    # 2026-01-05 is a Monday, no busy events. Full day 00:00-24:00 requested.
    calendar_working_hours_set(acl, "carol", "proj", "Europe/Stockholm", {"mon": [{"start": "09:00", "end": "17:00"}]})
    dav = _MockDav([])
    slots = calendar_find_free(
        acl, "carol", "proj",
        duration_min=30,
        within_start="2026-01-05T00:00:00+00:00",
        within_end="2026-01-06T00:00:00+00:00",
        _dav=dav,
    )
    assert slots == [{"start": "2026-01-05T08:00:00+00:00", "end": "2026-01-05T16:00:00+00:00"}]


def test_calendar_find_free_excludes_days_with_no_window(acl):
    # 2026-01-10 is a Saturday, "sat" not in the schedule at all.
    calendar_working_hours_set(acl, "carol", "proj", "Europe/Stockholm", {"mon": [{"start": "09:00", "end": "17:00"}]})
    dav = _MockDav([])
    slots = calendar_find_free(
        acl, "carol", "proj",
        duration_min=30,
        within_start="2026-01-10T00:00:00+00:00",
        within_end="2026-01-11T00:00:00+00:00",
        _dav=dav,
    )
    assert slots == []


def test_calendar_find_free_unaffected_when_no_schedule_configured(acl):
    dav = _MockDav([])
    slots = calendar_find_free(
        acl, "carol", "proj",
        duration_min=30,
        within_start="2026-01-10T00:00:00+00:00",
        within_end="2026-01-11T00:00:00+00:00",
        _dav=dav,
    )
    assert slots == [{"start": "2026-01-10T00:00:00+00:00", "end": "2026-01-11T00:00:00+00:00"}]
