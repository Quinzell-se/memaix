# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for notify.scheduler — next_brief_epoch and run_due."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from memaix_gateway.notify.scheduler import next_brief_epoch, run_due
from memaix_gateway.notify.store import NotifyStore


def test_next_brief_epoch_later_today():
    now = datetime(2026, 1, 15, 6, 0, tzinfo=timezone.utc)
    prefs = {"timezone": "UTC", "brief_time": "07:00"}
    epoch = next_brief_epoch(prefs, now)
    expected = int(datetime(2026, 1, 15, 7, 0, tzinfo=timezone.utc).timestamp())
    assert epoch == expected


def test_next_brief_epoch_rolls_to_tomorrow_if_passed():
    now = datetime(2026, 1, 15, 8, 0, tzinfo=timezone.utc)
    prefs = {"timezone": "UTC", "brief_time": "07:00"}
    epoch = next_brief_epoch(prefs, now)
    expected = int(datetime(2026, 1, 16, 7, 0, tzinfo=timezone.utc).timestamp())
    assert epoch == expected


def test_next_brief_epoch_respects_timezone():
    # 07:00 in Europe/Stockholm (UTC+1 in January) = 06:00 UTC.
    now = datetime(2026, 1, 15, 0, 0, tzinfo=timezone.utc)
    prefs = {"timezone": "Europe/Stockholm", "brief_time": "07:00"}
    epoch = next_brief_epoch(prefs, now)
    expected = int(datetime(2026, 1, 15, 6, 0, tzinfo=timezone.utc).timestamp())
    assert epoch == expected


@pytest.fixture()
def store(tmp_path):
    return NotifyStore.for_path(tmp_path / "notify.db")


def _seed(store, user="alice", **prefs_overrides):
    prefs = {"enabled": True, "timezone": "UTC", "brief_time": "07:00", "channels": [], "projects": []}
    prefs.update(prefs_overrides)
    store.set_prefs(user, now_iso="t0", **prefs)
    store.upsert_schedule(user, "daily", int(datetime(2026, 1, 15, 7, 0, tzinfo=timezone.utc).timestamp()))


def test_run_due_delivers_due_slot(store):
    _seed(store)
    now = datetime(2026, 1, 15, 7, 5, tzinfo=timezone.utc)
    calls = []
    ran = run_due(store, lambda user, prefs, now_: calls.append(user), now)
    assert ran == 1
    assert calls == ["alice"]
    # Rescheduled forward for tomorrow.
    sched = store.get_schedule("alice", "daily")
    assert sched["next_run"] > int(now.timestamp())


def test_run_due_skips_not_yet_due(store):
    _seed(store)
    now = datetime(2026, 1, 15, 6, 0, tzinfo=timezone.utc)  # before 07:00
    calls = []
    ran = run_due(store, lambda user, prefs, now_: calls.append(user), now)
    assert ran == 0
    assert calls == []


def test_run_due_skips_disabled_but_still_reschedules(store):
    _seed(store, enabled=False)
    now = datetime(2026, 1, 15, 7, 5, tzinfo=timezone.utc)
    calls = []
    ran = run_due(store, lambda user, prefs, now_: calls.append(user), now)
    assert ran == 0
    assert calls == []
    sched = store.get_schedule("alice", "daily")
    assert sched["next_run"] > int(now.timestamp())  # doesn't get stuck re-firing


def test_run_due_does_not_double_fire_same_tick(store):
    """Simulates two workers racing on the same DB at the same instant."""
    _seed(store)
    now = datetime(2026, 1, 15, 7, 5, tzinfo=timezone.utc)
    calls = []

    def deliver_fn(user, prefs, now_):
        calls.append(user)
        # Simulate a second worker's run_due happening concurrently, using the
        # SAME store — its claim() should fail since next_run already moved.
        second_ran = run_due(store, lambda u, p, n: calls.append("second-worker"), now)
        assert second_ran == 0

    ran = run_due(store, deliver_fn, now)
    assert ran == 1
    assert calls == ["alice"]  # second worker never got in


def test_run_due_failing_deliver_still_marks_run(store):
    _seed(store)
    now = datetime(2026, 1, 15, 7, 5, tzinfo=timezone.utc)

    def boom(user, prefs, now_):
        raise RuntimeError("smtp down")

    ran = run_due(store, boom, now)
    assert ran == 0  # deliver_fn raised, so it's not counted as delivered...
    # ...but mark_run still happened (finally-block) so history isn't stuck.
    sched = store.get_schedule("alice", "daily")
    assert sched["last_run"] == int(now.timestamp())
