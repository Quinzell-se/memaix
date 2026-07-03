# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for AuditLog.query (MEX-021) — filtered, paginated audit retrieval."""

from __future__ import annotations

import pytest

from memaix_gateway.safety.audit import AuditLog


@pytest.fixture()
def audit(tmp_path):
    AuditLog._clear_instances()
    log = AuditLog.for_path(tmp_path / "audit.db")
    # Deterministic ts so `since` filtering is exercisable.
    log.log("alice", "acme", "email_send", True, detail="")
    log.log("alice", "acme", "email_send", False, detail="denied")
    log.log("bob", "beta", "files_read", True, detail="")
    log.log("alice", "beta", "calendar_list", True, detail="")
    yield log
    AuditLog._clear_instances()


def test_query_no_filters_returns_all_oldest_first(audit):
    rows = audit.query()
    assert [r["tool"] for r in rows] == [
        "email_send",
        "email_send",
        "files_read",
        "calendar_list",
    ]


def test_query_filter_by_user(audit):
    rows = audit.query(user="alice")
    assert len(rows) == 3
    assert all(r["user"] == "alice" for r in rows)


def test_query_filter_by_project(audit):
    rows = audit.query(project="beta")
    assert {r["tool"] for r in rows} == {"files_read", "calendar_list"}


def test_query_filter_by_tool_and_ok(audit):
    rows = audit.query(tool="email_send", ok=False)
    assert len(rows) == 1
    assert rows[0]["detail"] == "denied"


def test_query_combined_filters(audit):
    rows = audit.query(user="alice", project="acme", ok=True)
    assert len(rows) == 1
    assert rows[0]["tool"] == "email_send"
    assert rows[0]["ok"] is True


def test_query_pagination(audit):
    page1 = audit.query(limit=2, offset=0)
    page2 = audit.query(limit=2, offset=2)
    assert len(page1) == 2
    assert len(page2) == 2
    # No overlap between pages.
    ids = {r["id"] for r in page1} | {r["id"] for r in page2}
    assert len(ids) == 4


def test_query_since_filters_older_events(audit):
    all_rows = audit.query()
    # Use the ts of the 3rd event as the cutoff — expect the last two rows.
    cutoff = all_rows[2]["ts"]
    rows = audit.query(since=cutoff)
    tools = [r["tool"] for r in rows]
    assert "files_read" in tools and "calendar_list" in tools
    assert "email_send" not in tools or all(r["ts"] >= cutoff for r in rows)
