# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for notify.store.NotifyStore."""

from __future__ import annotations

import pytest

from memaix_gateway.notify.store import NotifyStore


@pytest.fixture()
def store(tmp_path):
    return NotifyStore.for_path(tmp_path / "notify.db")


def test_set_and_get_prefs(store):
    prefs = store.set_prefs(
        "alice", now_iso="2026-01-01T00:00:00Z", enabled=True,
        brief_time="08:00", timezone="Europe/Stockholm", channels=[{"type": "email", "to": "a@b.com"}],
    )
    assert prefs["enabled"] is True
    assert prefs["brief_time"] == "08:00"
    fetched = store.get_prefs("alice")
    assert fetched == prefs


def test_get_prefs_missing_user_returns_none(store):
    assert store.get_prefs("nobody") is None


def test_set_prefs_partial_update_keeps_other_fields(store):
    store.set_prefs("alice", now_iso="t1", enabled=True, brief_time="08:00", timezone="UTC")
    updated = store.set_prefs("alice", now_iso="t2", enabled=False)
    assert updated["enabled"] is False
    assert updated["brief_time"] == "08:00"  # untouched


def test_schedule_upsert_and_due(store):
    store.upsert_schedule("alice", "daily", 1000)
    assert store.due(999) == []
    due = store.due(1000)
    assert len(due) == 1
    assert due[0]["memaix_user"] == "alice"


def test_claim_is_compare_and_set(store):
    store.upsert_schedule("alice", "daily", 1000)
    assert store.claim("alice", "daily", 1000, 2000) is True
    # Second claim with the old value fails — already moved on.
    assert store.claim("alice", "daily", 1000, 3000) is False
    assert store.get_schedule("alice", "daily")["next_run"] == 2000


def test_mark_run_updates_last_run(store):
    store.upsert_schedule("alice", "daily", 1000)
    store.mark_run("alice", "daily", 1000)
    assert store.get_schedule("alice", "daily")["last_run"] == 1000


def test_already_sent_before_and_after_record(store):
    assert store.already_sent("alice:daily:2026-01-01") is False
    store.record_sent("alice:daily:2026-01-01", "2026-01-01T07:00:00Z")
    assert store.already_sent("alice:daily:2026-01-01") is True


def test_record_sent_is_idempotent(store):
    store.record_sent("k", "t1")
    store.record_sent("k", "t2")  # should not raise (INSERT OR IGNORE)
    assert store.already_sent("k") is True
