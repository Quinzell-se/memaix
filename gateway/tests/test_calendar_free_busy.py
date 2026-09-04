# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for tools.calendar.calendar_free_busy — memaix-src card 4daa20e2."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from memaix_gateway.acl import Acl, AccessDenied
from memaix_gateway.tools.calendar import calendar_free_busy


def _dt(h: int) -> datetime:
    return datetime(2026, 1, 5, h, tzinfo=timezone.utc)


@pytest.fixture()
def acl(tmp_path):
    return Acl(
        users={
            "alice": {"grants": {"proj": "owner"}},
            "eve": {"grants": {}},
        },
        projects={"proj": {"vault": str(tmp_path), "calendar": {"type": "caldav"}}},
    )


def test_calendar_free_busy_denied_without_grant(acl):
    with pytest.raises(AccessDenied):
        calendar_free_busy(acl, "eve", "proj", _dt(0).isoformat(), _dt(23).isoformat())


def test_calendar_free_busy_never_synced_returns_empty_with_note(acl):
    result = calendar_free_busy(acl, "alice", "proj", _dt(0).isoformat(), _dt(23).isoformat(), _cache=None)
    assert result["busy"] == []
    assert result["stale"] is True
    assert result["synced_at"] is None
    assert "note" in result


def test_calendar_free_busy_returns_busy_within_range(acl):
    cache = {
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "busy": [{"start": _dt(9).isoformat(), "end": _dt(10).isoformat(), "source": "caldav:proj"}],
        "source_count": 1,
        "errors": [],
    }
    result = calendar_free_busy(acl, "alice", "proj", _dt(0).isoformat(), _dt(23).isoformat(), _cache=cache)
    assert result["busy"] == [{"start": _dt(9).isoformat(), "end": _dt(10).isoformat(), "source": "caldav:proj"}]
    assert result["stale"] is False
    assert result["source_count"] == 1


def test_calendar_free_busy_filters_out_events_outside_requested_range(acl):
    cache = {
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "busy": [{"start": _dt(9).isoformat(), "end": _dt(10).isoformat(), "source": "caldav:proj"}],
        "source_count": 1,
        "errors": [],
    }
    result = calendar_free_busy(acl, "alice", "proj", _dt(11).isoformat(), _dt(12).isoformat(), _cache=cache)
    assert result["busy"] == []


def test_calendar_free_busy_stale_when_cache_older_than_an_hour(acl):
    old = datetime.now(timezone.utc) - timedelta(hours=2)
    cache = {"synced_at": old.isoformat(), "busy": [], "source_count": 1, "errors": []}
    result = calendar_free_busy(acl, "alice", "proj", _dt(0).isoformat(), _dt(23).isoformat(), _cache=cache)
    assert result["stale"] is True


def test_calendar_free_busy_uses_events_when_present_and_honors_source_busy(acl):
    """memaix-src card c7698ff3 — a cache with "events" resolves per-event
    (honoring source_busy, e.g. Google transparency:transparent) instead of
    the pre-merged "busy" list."""
    cache = {
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "events": [
            {"uid": "e1", "start": _dt(9).isoformat(), "end": _dt(10).isoformat(), "source": "caldav:proj", "source_busy": True},
            {"uid": "e2", "start": _dt(11).isoformat(), "end": _dt(12).isoformat(), "source": "caldav:proj", "source_busy": False},
        ],
        "busy": [{"start": _dt(9).isoformat(), "end": _dt(10).isoformat(), "source": "caldav:proj"},
                 {"start": _dt(11).isoformat(), "end": _dt(12).isoformat(), "source": "caldav:proj"}],
        "source_count": 1,
        "errors": [],
    }
    result = calendar_free_busy(acl, "alice", "proj", _dt(0).isoformat(), _dt(23).isoformat(), _cache=cache)
    assert result["busy"] == [{"start": _dt(9).isoformat(), "end": _dt(10).isoformat(), "source": "caldav:proj"}]


def test_calendar_free_busy_honors_event_override(acl):
    from memaix_gateway.connectors.calendar_event_overrides import EventOverrideStore

    EventOverrideStore(acl, "proj", "alice").set_instance("caldav:proj", "e2", "busy")
    cache = {
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "events": [
            {"uid": "e2", "start": _dt(11).isoformat(), "end": _dt(12).isoformat(), "source": "caldav:proj", "source_busy": False},
        ],
        "busy": [],
        "source_count": 1,
        "errors": [],
    }
    result = calendar_free_busy(acl, "alice", "proj", _dt(0).isoformat(), _dt(23).isoformat(), _cache=cache)
    assert result["busy"] == [{"start": _dt(11).isoformat(), "end": _dt(12).isoformat(), "source": "caldav:proj"}]


def test_calendar_free_busy_surfaces_source_errors(acl):
    cache = {
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "busy": [],
        "source_count": 2,
        "errors": [{"source": "caldav:proj", "error": "timeout"}],
    }
    result = calendar_free_busy(acl, "alice", "proj", _dt(0).isoformat(), _dt(23).isoformat(), _cache=cache)
    assert result["errors"] == [{"source": "caldav:proj", "error": "timeout"}]
