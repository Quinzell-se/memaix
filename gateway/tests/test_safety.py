# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for safety/ — rate limiter and audit log."""

from __future__ import annotations

import time

import pytest

from memaix_gateway.safety.audit import AuditLog
from memaix_gateway.safety.rate_limit import (
    RateLimiter,
    SQLiteRateLimiter,
    make_rate_limiter,
)


# ------------------------------------------------------------------
# RateLimiter
# ------------------------------------------------------------------


@pytest.fixture()
def limiter():
    return RateLimiter()


def test_check_user_passes_within_limit(limiter):
    for _ in range(60):
        assert limiter.check_user("alice") is True


def test_check_user_denied_on_61st(limiter):
    for _ in range(60):
        limiter.check_user("bob")
    assert limiter.check_user("bob") is False


def test_check_project_passes_within_limit(limiter):
    for _ in range(120):
        assert limiter.check_project("myproject") is True


def test_check_project_denied_on_121st(limiter):
    for _ in range(120):
        limiter.check_project("myproject2")
    assert limiter.check_project("myproject2") is False


def test_sliding_window_old_calls_expire(limiter):
    key = "user:expiry_test"
    # Fill to limit
    for _ in range(60):
        limiter.check(key, limit=60, window_s=60)
    assert limiter.check(key, limit=60, window_s=60) is False

    # Age all existing timestamps to before the window
    now = time.monotonic()
    old_ts = [now - 61.0] * 60
    limiter._inject_timestamps(key, old_ts)

    # Now the window is clear — new call should pass
    assert limiter.check(key, limit=60, window_s=60) is True


def test_different_users_independent(limiter):
    for _ in range(60):
        limiter.check_user("user_a")
    # user_a exhausted, user_b unaffected
    assert limiter.check_user("user_b") is True


def test_check_returns_bool(limiter):
    result = limiter.check("some_key", limit=10, window_s=30)
    assert isinstance(result, bool)


# ------------------------------------------------------------------
# SQLiteRateLimiter — same behaviour, persistent/shared backend
# ------------------------------------------------------------------


@pytest.fixture()
def sqlite_limiter(tmp_path):
    return SQLiteRateLimiter(tmp_path / "rl.db")


def test_sqlite_limiter_enforces_limit(sqlite_limiter):
    for _ in range(60):
        assert sqlite_limiter.check_user("alice") is True
    assert sqlite_limiter.check_user("alice") is False


def test_sqlite_limiter_independent_keys(sqlite_limiter):
    for _ in range(60):
        sqlite_limiter.check_user("a")
    assert sqlite_limiter.check_user("b") is True


def test_sqlite_limiter_window_expiry(sqlite_limiter):
    key = "user:exp"
    for _ in range(60):
        sqlite_limiter.check(key, limit=60, window_s=60)
    assert sqlite_limiter.check(key, limit=60, window_s=60) is False
    sqlite_limiter._inject_timestamps(key, [time.time() - 61.0] * 60)
    assert sqlite_limiter.check(key, limit=60, window_s=60) is True


def test_sqlite_limiter_shares_state_across_instances(tmp_path):
    """A second instance on the same DB sees the first's counts (multi-worker)."""
    db = tmp_path / "shared.db"
    a = SQLiteRateLimiter(db)
    b = SQLiteRateLimiter(db)
    for _ in range(60):
        a.check_user("dave")
    assert b.check_user("dave") is False


def test_make_rate_limiter_backends(tmp_path, monkeypatch):
    monkeypatch.delenv("MEMAIX_RATELIMIT_BACKEND", raising=False)
    assert isinstance(make_rate_limiter(), RateLimiter)
    monkeypatch.setenv("MEMAIX_RATELIMIT_BACKEND", "sqlite")
    monkeypatch.setenv("MEMAIX_RATELIMIT_DB", str(tmp_path / "made.db"))
    assert isinstance(make_rate_limiter(), SQLiteRateLimiter)


# ------------------------------------------------------------------
# AuditLog
# ------------------------------------------------------------------


@pytest.fixture()
def audit(tmp_path):
    AuditLog._clear_instances()
    db = tmp_path / "test-audit.db"
    return AuditLog.for_path(db)


def test_audit_log_and_tail(audit):
    audit.log("alice", "proj", "memory_read", True)
    audit.log("carol", "proj", "memory_write", True)
    audit.log("alice", "proj", "memory_read", False, "not found")

    events = audit.tail(50)
    assert len(events) == 3


def test_audit_tail_oldest_first(audit):
    audit.log("u1", "p", "tool_a", True)
    audit.log("u2", "p", "tool_b", False)

    events = audit.tail()
    assert events[0]["tool"] == "tool_a"
    assert events[1]["tool"] == "tool_b"


def test_audit_fields_stored_correctly(audit):
    audit.log("alice", "myproj", "email_send", False, "rate limited")
    events = audit.tail()
    ev = events[0]
    assert ev["user"] == "alice"
    assert ev["project"] == "myproj"
    assert ev["tool"] == "email_send"
    assert ev["ok"] is False
    assert ev["detail"] == "rate limited"
    assert "ts" in ev


def test_audit_tail_limit(audit):
    for i in range(10):
        audit.log("u", "p", f"tool_{i}", True)
    events = audit.tail(limit=3)
    assert len(events) == 3


def test_audit_for_vault_uses_memaix_db(tmp_path):
    AuditLog._clear_instances()
    vault = tmp_path / "vault"
    vault.mkdir()
    al = AuditLog.for_vault(vault)
    al.log("alice", "proj", "files_read", True)
    assert (vault / ".memaix.db").exists()
    events = al.tail()
    assert len(events) == 1
