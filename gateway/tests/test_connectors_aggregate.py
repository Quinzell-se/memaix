# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for connectors.aggregate — memaix-src card 4daa20e2."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from memaix_gateway.connectors.aggregate import (
    BusyInterval,
    CalendarEvent,
    CalendarSourceError,
    busy_from_backend,
    events_from_backend,
    free_slots,
    merge_busy,
    to_utc,
)


def _dt(h: int, m: int = 0) -> datetime:
    return datetime(2026, 1, 5, h, m, tzinfo=timezone.utc)


class _FakeBackend:
    def __init__(self, events=None, raises=None):
        self._events = events or []
        self._raises = raises

    def list_events(self, start, end):
        if self._raises:
            raise self._raises
        return self._events


def test_to_utc_assumes_utc_for_naive_input():
    naive = datetime(2026, 1, 5, 10, 0)
    assert to_utc(naive) == _dt(10)


def test_to_utc_parses_iso_string():
    assert to_utc("2026-01-05T10:00:00+00:00") == _dt(10)


def test_merge_busy_disjoint_blocks_stay_separate():
    a = BusyInterval(_dt(9), _dt(10), "a")
    b = BusyInterval(_dt(14), _dt(15), "b")
    assert merge_busy([b, a]) == [a, b]


def test_merge_busy_overlapping_blocks_coalesce():
    a = BusyInterval(_dt(9), _dt(11), "a")
    b = BusyInterval(_dt(10), _dt(12), "b")
    merged = merge_busy([a, b])
    assert merged == [BusyInterval(_dt(9), _dt(12), "a")]


def test_merge_busy_adjacent_blocks_coalesce():
    a = BusyInterval(_dt(9), _dt(10), "a")
    b = BusyInterval(_dt(10), _dt(11), "b")
    merged = merge_busy([a, b])
    assert merged == [BusyInterval(_dt(9), _dt(11), "a")]


def test_merge_busy_empty_input():
    assert merge_busy([]) == []


def test_free_slots_gap_shorter_than_duration_is_dropped():
    busy = [BusyInterval(_dt(9), _dt(9, 50), "a"), BusyInterval(_dt(10, 20), _dt(11), "a")]
    slots = free_slots(busy, _dt(9), _dt(12), timedelta(minutes=30))
    assert slots == [{"start": _dt(11).isoformat(), "end": _dt(12).isoformat()}]


def test_free_slots_fully_free_range():
    slots = free_slots([], _dt(9), _dt(10), timedelta(minutes=30))
    assert slots == [{"start": _dt(9).isoformat(), "end": _dt(10).isoformat()}]


def test_free_slots_fully_busy_range():
    busy = [BusyInterval(_dt(9), _dt(10), "a")]
    assert free_slots(busy, _dt(9), _dt(10), timedelta(minutes=30)) == []


def test_free_slots_never_leaks_source_or_event_identity():
    # memaix-src card de858332 — an external booking view merges busy
    # intervals from every calendar source in the aggregate, but must only
    # ever expose whether a slot is free, never which source or event it
    # came from. BusyInterval carries a "source" tag for internal merge
    # logic (merge_busy) — assert it never reaches free_slots' output.
    busy = [BusyInterval(_dt(9), _dt(9, 30), "google:alice@example.com")]
    slots = free_slots(busy, _dt(9), _dt(11), timedelta(minutes=30))
    assert len(slots) >= 1
    for s in slots:
        assert set(s.keys()) == {"start", "end"}


def test_busy_from_backend_normalises_events():
    backend = _FakeBackend(events=[{"start": "2026-01-05T09:00:00+00:00", "end": "2026-01-05T10:00:00+00:00"}])
    result = busy_from_backend(backend, "src1", _dt(0), _dt(23))
    assert result == [BusyInterval(_dt(9), _dt(10), "src1")]


def test_busy_from_backend_skips_malformed_event():
    backend = _FakeBackend(events=[{"start": "not-a-date", "end": "2026-01-05T10:00:00+00:00"}])
    assert busy_from_backend(backend, "src1", _dt(0), _dt(23)) == []


def test_busy_from_backend_wraps_adapter_failure():
    backend = _FakeBackend(raises=RuntimeError("boom"))
    with pytest.raises(CalendarSourceError) as exc_info:
        busy_from_backend(backend, "src1", _dt(0), _dt(23))
    assert exc_info.value.label == "src1"
    assert isinstance(exc_info.value.cause, RuntimeError)


def test_events_from_backend_preserves_identity_and_series_fields():
    backend = _FakeBackend(events=[{
        "id": "ev1", "title": "Sync", "start": "2026-01-05T09:00:00+00:00", "end": "2026-01-05T10:00:00+00:00",
        "series_id": "series-1", "is_exception": True, "source_busy": False,
    }])
    result = events_from_backend(backend, "src1", _dt(0), _dt(23))
    assert result == [
        CalendarEvent(
            uid="ev1", start=_dt(9), end=_dt(10), source="src1", title="Sync",
            series_id="series-1", is_exception=True, source_busy=False,
        )
    ]


def test_events_from_backend_defaults_missing_series_fields():
    backend = _FakeBackend(events=[{"id": "ev1", "start": "2026-01-05T09:00:00+00:00", "end": "2026-01-05T10:00:00+00:00"}])
    result = events_from_backend(backend, "src1", _dt(0), _dt(23))
    assert result == [CalendarEvent(uid="ev1", start=_dt(9), end=_dt(10), source="src1")]


def test_events_from_backend_synthesizes_uid_when_missing():
    """An event with no id still counts (matches busy_from_backend's old
    unconditional behavior) — it just gets a synthetic, non-stable uid."""
    backend = _FakeBackend(events=[{"start": "2026-01-05T09:00:00+00:00", "end": "2026-01-05T10:00:00+00:00"}])
    result = events_from_backend(backend, "src1", _dt(0), _dt(23))
    assert len(result) == 1
    assert result[0].uid == "src1-0"


def test_events_from_backend_skips_malformed_event():
    backend = _FakeBackend(events=[{"id": "ev1", "start": "not-a-date", "end": "2026-01-05T10:00:00+00:00"}])
    assert events_from_backend(backend, "src1", _dt(0), _dt(23)) == []


def test_events_from_backend_wraps_adapter_failure():
    backend = _FakeBackend(raises=RuntimeError("boom"))
    with pytest.raises(CalendarSourceError) as exc_info:
        events_from_backend(backend, "src1", _dt(0), _dt(23))
    assert exc_info.value.label == "src1"
