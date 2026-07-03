# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for outbox.queue.ActionQueue."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from memaix_gateway.outbox.queue import ActionQueue


@pytest.fixture()
def queue(tmp_path):
    return ActionQueue.for_path(tmp_path / "outbox.db")


def test_enqueue_and_get(queue):
    aid = queue.enqueue("alice", "proj", "email_send", {"to": "x@y.com"}, "preview text")
    action = queue.get(aid)
    assert action["memaix_user"] == "alice"
    assert action["project"] == "proj"
    assert action["tool"] == "email_send"
    assert action["args"] == {"to": "x@y.com"}
    assert action["status"] == "pending"


def test_get_missing_returns_none(queue):
    assert queue.get("does-not-exist") is None


def test_list_filters_by_project_and_status(queue):
    queue.enqueue("alice", "proj-a", "email_send", {}, "p1")
    queue.enqueue("alice", "proj-b", "email_send", {}, "p2")
    assert len(queue.list(["proj-a"])) == 1
    assert len(queue.list(["proj-a", "proj-b"])) == 2
    assert queue.list([]) == []


def test_list_status_filter(queue):
    aid = queue.enqueue("alice", "proj", "email_send", {}, "p")
    queue.claim_for_decision(aid, "approved", "alice")
    assert len(queue.list(["proj"], "pending")) == 0
    assert len(queue.list(["proj"], "approved")) == 1


def test_claim_for_decision_idempotent(queue):
    aid = queue.enqueue("alice", "proj", "email_send", {}, "p")
    first = queue.claim_for_decision(aid, "approved", "bob")
    assert first is not None
    assert first["status"] == "approved"
    assert first["decided_by"] == "bob"

    second = queue.claim_for_decision(aid, "rejected", "carol")
    assert second is None  # already decided — no double-decision


def test_claim_for_decision_unknown_id_returns_none(queue):
    assert queue.claim_for_decision("nope", "approved", "alice") is None


def test_claim_for_decision_stores_reason(queue):
    aid = queue.enqueue("alice", "proj", "email_send", {}, "p")
    claimed = queue.claim_for_decision(aid, "rejected", "bob", reason="wrong recipient")
    assert claimed["reason"] == "wrong recipient"


def test_record_result(queue):
    aid = queue.enqueue("alice", "proj", "email_send", {}, "p")
    queue.claim_for_decision(aid, "approved", "alice")
    queue.record_result(aid, "executed", {"status": "sent"})
    action = queue.get(aid)
    assert action["status"] == "executed"
    assert action["result"] == {"status": "sent"}


def test_expire_due(queue):
    aid = queue.enqueue("alice", "proj", "email_send", {}, "p", ttl_h=-1)  # already expired
    count = queue.expire_due(datetime.now(timezone.utc).isoformat())
    assert count == 1
    assert queue.get(aid)["status"] == "expired"


def test_expire_due_skips_future(queue):
    queue.enqueue("alice", "proj", "email_send", {}, "p", ttl_h=72)
    count = queue.expire_due(datetime.now(timezone.utc).isoformat())
    assert count == 0
