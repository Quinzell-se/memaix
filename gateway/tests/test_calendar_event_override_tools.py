# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for tools.calendar.calendar_events_list/calendar_event_override_set/
calendar_event_override_clear — memaix-src card c7698ff3."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from memaix_gateway.acl import Acl, AccessDenied
from memaix_gateway.tools.calendar import (
    calendar_event_override_clear,
    calendar_event_override_set,
    calendar_events_list,
)


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


def _cache(**events_kwargs):
    return {
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "events": [
            {
                "uid": "e1", "start": _dt(9).isoformat(), "end": _dt(10).isoformat(),
                "source": "caldav:proj", "title": "Sync", "source_busy": True,
                "series_id": None, "is_exception": False,
                **events_kwargs,
            }
        ],
    }


def test_calendar_events_list_denied_without_grant(acl):
    with pytest.raises(AccessDenied):
        calendar_events_list(acl, "eve", "proj", _dt(0).isoformat(), _dt(23).isoformat())


def test_calendar_events_list_never_synced_returns_empty(acl):
    result = calendar_events_list(acl, "alice", "proj", _dt(0).isoformat(), _dt(23).isoformat(), _cache=None)
    assert result == {"events": [], "synced_at": None, "stale": True}


def test_calendar_events_list_returns_event_with_no_override(acl):
    result = calendar_events_list(acl, "alice", "proj", _dt(0).isoformat(), _dt(23).isoformat(), _cache=_cache())
    assert len(result["events"]) == 1
    ev = result["events"][0]
    assert ev["uid"] == "e1"
    assert ev["override"] is None
    assert ev["effective_busy"] is True
    assert ev["in_series"] is False
    assert ev["overridable"] is True


def test_calendar_events_list_in_series_true_when_series_id_set(acl):
    cache = _cache(series_id="series-1")
    result = calendar_events_list(acl, "alice", "proj", _dt(0).isoformat(), _dt(23).isoformat(), _cache=cache)
    assert result["events"][0]["in_series"] is True


def test_calendar_events_list_filters_outside_range(acl):
    result = calendar_events_list(acl, "alice", "proj", _dt(11).isoformat(), _dt(12).isoformat(), _cache=_cache())
    assert result["events"] == []


def test_calendar_event_override_set_instance_denied_without_grant(acl):
    with pytest.raises(AccessDenied):
        calendar_event_override_set(acl, "eve", "proj", "caldav:proj", "busy", uid="e1")


def test_calendar_event_override_set_instance_requires_uid(acl):
    result = calendar_event_override_set(acl, "alice", "proj", "caldav:proj", "busy", scope="instance")
    assert result == {"ok": False, "error": "uid krävs för scope=instance"}


def test_calendar_event_override_set_series_requires_series_id(acl):
    result = calendar_event_override_set(acl, "alice", "proj", "caldav:proj", "busy", scope="series")
    assert result == {"ok": False, "error": "series_id krävs för scope=series"}


def test_calendar_event_override_set_rejects_invalid_state(acl):
    result = calendar_event_override_set(acl, "alice", "proj", "caldav:proj", "maybe", uid="e1")
    assert result["ok"] is False


def test_calendar_event_override_set_rejects_invalid_scope(acl):
    result = calendar_event_override_set(acl, "alice", "proj", "caldav:proj", "busy", scope="bulk", uid="e1")
    assert result["ok"] is False


def test_calendar_event_override_set_instance_then_reflected_in_events_list(acl):
    calendar_event_override_set(acl, "alice", "proj", "caldav:proj", "free", uid="e1")
    result = calendar_events_list(acl, "alice", "proj", _dt(0).isoformat(), _dt(23).isoformat(), _cache=_cache())
    assert result["events"][0]["override"] == "free"
    assert result["events"][0]["effective_busy"] is False


def test_calendar_event_override_set_series_ignored_by_exception_instance(acl):
    calendar_event_override_set(acl, "alice", "proj", "caldav:proj", "busy", scope="series", series_id="series-1")
    cache = _cache(series_id="series-1", is_exception=True, source_busy=False)
    result = calendar_events_list(acl, "alice", "proj", _dt(0).isoformat(), _dt(23).isoformat(), _cache=cache)
    # exception instance does not inherit the series override
    assert result["events"][0]["override"] is None
    assert result["events"][0]["effective_busy"] is False


def test_calendar_event_override_clear_instance(acl):
    calendar_event_override_set(acl, "alice", "proj", "caldav:proj", "free", uid="e1")
    result = calendar_event_override_clear(acl, "alice", "proj", "caldav:proj", uid="e1")
    assert result == {"ok": True, "removed": True}


def test_calendar_event_override_clear_missing_returns_removed_false(acl):
    result = calendar_event_override_clear(acl, "alice", "proj", "caldav:proj", uid="nope")
    assert result == {"ok": True, "removed": False}


def test_calendar_event_override_clear_requires_uid_for_instance(acl):
    result = calendar_event_override_clear(acl, "alice", "proj", "caldav:proj", scope="instance")
    assert result == {"ok": False, "error": "uid krävs för scope=instance"}


def test_calendar_event_override_clear_requires_series_id_for_series(acl):
    result = calendar_event_override_clear(acl, "alice", "proj", "caldav:proj", scope="series")
    assert result == {"ok": False, "error": "series_id krävs för scope=series"}
