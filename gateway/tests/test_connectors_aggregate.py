# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for connectors.aggregate — memaix-src card 4daa20e2."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from memaix_gateway.connectors.aggregate import (
    BusyInterval,
    CalendarSourceError,
    busy_from_backend,
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
