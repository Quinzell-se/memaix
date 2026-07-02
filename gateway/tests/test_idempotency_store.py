# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for safety.idempotency.IdempotencyStore (docs/OPEN-GAPS.md #13)."""

from __future__ import annotations

import pytest

from memaix_gateway.safety.idempotency import IdempotencyStore


@pytest.fixture()
def store(tmp_path):
    return IdempotencyStore.for_path(tmp_path / "idem.db")


def test_get_missing_key_returns_none(store):
    assert store.get("alice", "email_send", "k1") is None


def test_record_then_get_returns_cached_result(store):
    store.record("alice", "email_send", "k1", {"status": "sent", "to": "x@y.com"})
    assert store.get("alice", "email_send", "k1") == {"status": "sent", "to": "x@y.com"}


def test_scoped_by_user_tool_and_key(store):
    store.record("alice", "email_send", "k1", {"a": 1})
    assert store.get("bob", "email_send", "k1") is None  # different user
    assert store.get("alice", "calendar_create", "k1") is None  # different tool
    assert store.get("alice", "email_send", "k2") is None  # different key


def test_record_is_first_write_wins(store):
    store.record("alice", "email_send", "k1", {"attempt": 1})
    store.record("alice", "email_send", "k1", {"attempt": 2})
    assert store.get("alice", "email_send", "k1") == {"attempt": 1}


def test_purge_older_than(store):
    store.record("alice", "email_send", "k1", {"a": 1})
    store.purge_older_than("2999-01-01T00:00:00+00:00")
    assert store.get("alice", "email_send", "k1") is None
