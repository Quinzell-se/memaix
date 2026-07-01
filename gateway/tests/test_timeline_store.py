# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for timeline.store.ActionsStore."""

from __future__ import annotations

import pytest

from memaix_gateway.timeline.store import ActionsStore


@pytest.fixture()
def store(tmp_path):
    return ActionsStore.for_path(tmp_path / "actions.db")


def test_record_and_get_reversible(store):
    aid = store.record("alice", "proj", "memory_write", "Skrev x", {"tool": "memory_revert", "args": {"commit": "abc"}})
    action = store.get(aid)
    assert action["reversible"] is True
    assert action["inverse"] == {"tool": "memory_revert", "args": {"commit": "abc"}}
    assert action["status"] == "done"


def test_record_irreversible_when_inverse_none(store):
    aid = store.record("alice", "proj", "email_send", "Skickade mejl", None)
    action = store.get(aid)
    assert action["reversible"] is False
    assert action["inverse"] is None


def test_list_ordered_newest_first(store):
    a1 = store.record("alice", "proj", "memory_write", "first", None)
    a2 = store.record("alice", "proj", "memory_write", "second", None)
    listed = store.list(["proj"])
    assert [a["id"] for a in listed] == [a2, a1]


def test_list_filters_by_project(store):
    store.record("alice", "proj-a", "memory_write", "a", None)
    store.record("alice", "proj-b", "memory_write", "b", None)
    assert len(store.list(["proj-a"])) == 1
    assert len(store.list(["proj-a", "proj-b"])) == 2
    assert store.list([]) == []


def test_list_respects_limit(store):
    for i in range(5):
        store.record("alice", "proj", "memory_write", f"item {i}", None)
    assert len(store.list(["proj"], limit=2)) == 2


def test_claim_undo_idempotent(store):
    aid = store.record("alice", "proj", "memory_write", "x", {"tool": "memory_revert", "args": {}})
    first = store.claim_undo(aid)
    assert first is not None
    assert store.get(aid)["status"] == "undone"

    second = store.claim_undo(aid)
    assert second is None  # already undone — no double-undo


def test_claim_undo_rejects_irreversible(store):
    aid = store.record("alice", "proj", "email_send", "x", None)
    assert store.claim_undo(aid) is None
    assert store.get(aid)["status"] == "done"


def test_claim_undo_unknown_id(store):
    assert store.claim_undo("nope") is None


def test_mark_undo_failed(store):
    aid = store.record("alice", "proj", "memory_write", "x", {"tool": "memory_revert", "args": {}})
    store.claim_undo(aid)
    store.mark_undo_failed(aid)
    assert store.get(aid)["status"] == "undo_failed"


def test_link_undo(store):
    original = store.record("alice", "proj", "memory_write", "x", {"tool": "memory_revert", "args": {}})
    store.claim_undo(original)
    undo_id = store.record("alice", "proj", "memory_revert", "Ångrade: x", None, undo_of=original)
    store.link_undo(original, undo_id)
    action = store.get(original)
    assert action["undo_action_id"] == undo_id
    assert store.get(undo_id)["undo_of"] == original


def test_purge_older_than(store):
    aid = store.record("alice", "proj", "memory_write", "x", None)
    # Everything created before "now + 1 day" gets purged.
    from datetime import datetime, timedelta, timezone
    cutoff = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    removed = store.purge_older_than(cutoff)
    assert removed == 1
    assert store.get(aid) is None
