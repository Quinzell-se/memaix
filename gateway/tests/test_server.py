# SPDX-License-Identifier: AGPL-3.0-or-later
"""Smoke tests for the server-layer tool wrappers (_tool_call).

Drives tools through the FastMCP-registered functions in stdio mode
(MEMAIX_USER) to verify the shared identity + rate-limit + ACL + audit path.
"""

from __future__ import annotations

import time

import pytest

from memaix_gateway import server
from memaix_gateway.acl import AccessDenied, Acl
from memaix_gateway.outbox.queue import ActionQueue
from memaix_gateway.safety.audit import AuditLog
from memaix_gateway.search.embedder import FakeEmbedder
from memaix_gateway.search.store import EmbeddingStore
from memaix_gateway.timeline.store import ActionsStore


@pytest.fixture()
def wired(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    (vault / "backlog").mkdir(parents=True)
    acl = Acl(
        users={
            "alice": {"grants": {"proj": "owner"}},
            "bob": {"grants": {"proj": "reader"}},
        },
        projects={"proj": {"vault": str(vault)}},
    )
    AuditLog._clear_instances()
    monkeypatch.setattr(server, "_acl", acl)
    monkeypatch.setattr(server, "_audit", AuditLog.for_path(tmp_path / "audit.db"))
    monkeypatch.setattr(server, "_outbox_queue", ActionQueue.for_path(tmp_path / "outbox.db"))
    monkeypatch.setattr(server, "_timeline_store", ActionsStore.for_path(tmp_path / "actions.db"))
    monkeypatch.setattr(server, "_search_store", EmbeddingStore.for_path(tmp_path / "index.db"))
    monkeypatch.setattr(server, "_search_embedder", None)
    monkeypatch.setattr(server, "_search_embedder_loaded", True)  # skip config.load(); no embedder by default
    monkeypatch.setenv("MEMAIX_USER", "alice")
    server._rate_limiter._windows.clear()
    return vault, acl


def test_files_roundtrip_via_server(wired):
    server.files_write("proj", "/notes.txt", "hello")
    assert server.files_read("proj", "/notes.txt") == "hello"


def test_backlog_via_server_records_audit(wired):
    r = server.backlog_add("proj", "Title", "Body")
    assert server.backlog_get("proj", r["id"])["title"] == "Title"
    tools = [e["tool"] for e in server._get_audit().tail(20)]
    assert "backlog_add" in tools and "backlog_get" in tools


def test_server_enforces_acl(wired, monkeypatch):
    # bob is only a reader; files_read requires collaborator.
    monkeypatch.setenv("MEMAIX_USER", "bob")
    with pytest.raises(AccessDenied):
        server.files_read("proj", "/notes.txt")


def test_server_enforces_rate_limit(wired):
    # Fill the user's window so the next call is denied.
    server._rate_limiter._inject_timestamps("user:alice", [time.monotonic()] * 60)
    with pytest.raises(RuntimeError, match="rate_limited"):
        server.memory_search("proj", "anything")


def test_failed_tool_call_is_audited(wired):
    with pytest.raises(Exception):
        server.backlog_get("proj", "../../escape")  # blocked by path validation
    last = server._get_audit().tail(5)
    assert any(e["tool"] == "backlog_get" and e["ok"] is False for e in last)


# ------------------------------------------------------------------
# TOKEN_MASTER_KEY hardening
# ------------------------------------------------------------------


def test_http_mode_requires_master_key(monkeypatch):
    monkeypatch.setattr(server, "_token_store", None)
    monkeypatch.delenv("TOKEN_MASTER_KEY", raising=False)
    monkeypatch.delenv("MEMAIX_ALLOW_EPHEMERAL_KEY", raising=False)
    monkeypatch.setenv("MEMAIX_TRANSPORT", "http")
    with pytest.raises(RuntimeError, match="TOKEN_MASTER_KEY"):
        server._get_token_store()


def test_http_mode_ephemeral_opt_in(monkeypatch):
    monkeypatch.setattr(server, "_token_store", None)
    monkeypatch.delenv("TOKEN_MASTER_KEY", raising=False)
    monkeypatch.setenv("MEMAIX_TRANSPORT", "http")
    monkeypatch.setenv("MEMAIX_ALLOW_EPHEMERAL_KEY", "1")
    with pytest.warns(RuntimeWarning):
        store = server._get_token_store()
    assert store is not None


def test_stdio_mode_allows_ephemeral_key(monkeypatch):
    monkeypatch.setattr(server, "_token_store", None)
    monkeypatch.delenv("TOKEN_MASTER_KEY", raising=False)
    monkeypatch.delenv("MEMAIX_TRANSPORT", raising=False)
    monkeypatch.delenv("MEMAIX_ALLOW_EPHEMERAL_KEY", raising=False)
    with pytest.warns(RuntimeWarning):
        store = server._get_token_store()
    assert store is not None


# ------------------------------------------------------------------
# Outbox tools (FEATURE-APPROVAL-OUTBOX.md)
# ------------------------------------------------------------------


def test_outbox_list_and_get_via_server(wired):
    aid = server._get_outbox().enqueue("alice", "proj", "email_send", {"to": "x@y.com"}, "p")
    listed = server.outbox_list("proj", "pending")
    assert any(a["id"] == aid for a in listed)
    fetched = server.outbox_get(aid)
    assert fetched["id"] == aid


def test_outbox_get_denied_for_invisible_project(wired):
    aid = server._get_outbox().enqueue("alice", "other-proj", "email_send", {}, "p")
    with pytest.raises(AccessDenied):
        server.outbox_get(aid)


def test_outbox_approve_executes_and_is_idempotent(wired, monkeypatch):
    aid = server._get_outbox().enqueue(
        "alice", "proj", "email_send", {"to": "x@y.com", "subject": "s", "body": "b", "cc": None}, "p"
    )
    calls = []

    def fake_email_send(acl, user, project, **kwargs):
        calls.append(kwargs)
        return {"status": "sent"}

    monkeypatch.setattr(
        "memaix_gateway.outbox.execute._default_dispatch",
        lambda: {"email_send": fake_email_send},
    )

    result = server.outbox_approve(aid)
    assert result["ok"] is True
    assert calls[0]["_confirmed"] is True
    assert server.outbox_get(aid)["status"] == "executed"

    # Second approval on the same action is a no-op conflict, not a re-send.
    second = server.outbox_approve(aid)
    assert second["conflict"] is True
    assert len(calls) == 1


def test_outbox_approve_requires_correct_role(wired):
    aid = server._get_outbox().enqueue("alice", "proj", "email_send", {"to": "x@y.com"}, "p")
    import os
    os.environ["MEMAIX_USER"] = "bob"  # reader — email_send needs owner
    try:
        with pytest.raises(AccessDenied):
            server.outbox_approve(aid)
    finally:
        os.environ["MEMAIX_USER"] = "alice"
    assert server.outbox_get(aid)["status"] == "pending"


def test_outbox_reject_never_executes(wired, monkeypatch):
    aid = server._get_outbox().enqueue("alice", "proj", "email_send", {"to": "x@y.com"}, "p")
    calls = []
    monkeypatch.setattr(
        "memaix_gateway.outbox.execute._default_dispatch",
        lambda: {"email_send": lambda *a, **kw: calls.append(1) or {"status": "sent"}},
    )
    result = server.outbox_reject(aid, reason="not needed")
    assert result["status"] == "rejected"
    assert calls == []
    assert server.outbox_get(aid)["status"] == "rejected"

    # Rejecting again is a conflict, not a second decision.
    second = server.outbox_reject(aid)
    assert second["conflict"] is True


def test_outbox_approve_records_failure_on_exception(wired, monkeypatch):
    aid = server._get_outbox().enqueue("alice", "proj", "email_send", {"to": "x@y.com"}, "p")

    def boom(*a, **kw):
        raise RuntimeError("smtp unreachable")

    monkeypatch.setattr(
        "memaix_gateway.outbox.execute._default_dispatch",
        lambda: {"email_send": boom},
    )
    result = server.outbox_approve(aid)
    assert result["ok"] is False
    assert server.outbox_get(aid)["status"] == "failed"


# ------------------------------------------------------------------
# Timeline tools (FEATURE-UNDO-TIMELINE.md)
# ------------------------------------------------------------------


def test_memory_write_via_server_is_recorded_and_undoable(wired):
    server.memory_write("proj", "notes/x.md", "hello")
    entries = server.timeline_list("proj")
    assert len(entries) == 1
    assert entries[0]["tool"] == "memory_write"
    assert entries[0]["reversible"] is True

    hist_before = server.memory_history("proj", "notes/x.md")
    result = server.timeline_undo(entries[0]["id"])
    assert result["ok"] is True
    hist_after = server.memory_history("proj", "notes/x.md")
    assert len(hist_after) > len(hist_before)  # memory_revert added a new commit

    all_entries = server.timeline_list("proj")
    assert any(e.get("undo_of") == entries[0]["id"] for e in all_entries)


def test_backlog_add_via_server_is_recorded_and_undoable(wired):
    r = server.backlog_add("proj", "New idea", "desc")
    entries = server.timeline_list("proj")
    add_entry = next(e for e in entries if e["tool"] == "backlog_add")
    assert add_entry["reversible"] is True

    result = server.timeline_undo(add_entry["id"])
    assert result["ok"] is True
    item = server.backlog_get("proj", r["id"])
    assert item["status"] == "rejected"


def test_timeline_undo_second_call_refuses(wired):
    server.memory_write("proj", "notes/x.md", "hello")
    aid = server.timeline_list("proj")[0]["id"]
    assert server.timeline_undo(aid)["ok"] is True
    second = server.timeline_undo(aid)
    assert second["ok"] is False


def test_failed_tool_call_is_not_recorded_in_timeline(wired, monkeypatch):
    monkeypatch.setenv("MEMAIX_USER", "bob")  # reader — can't write memory
    with pytest.raises(Exception):
        server.memory_write("proj", "notes/x.md", "hello")
    monkeypatch.setenv("MEMAIX_USER", "alice")
    assert server.timeline_list("proj") == []


def test_timeline_list_filters_invisible_projects(wired):
    server.memory_write("proj", "notes/x.md", "hello")
    # Alice can't see a project she has no grant on.
    other_entries = server.timeline_list("no-such-project")
    assert other_entries == []


def test_queued_outbox_action_is_not_recorded_in_timeline(wired):
    """A tool result of {'pending': True, ...} means nothing happened yet —
    it must not show up in the timeline until it's actually approved/executed."""
    server._maybe_record_timeline(
        "alice", "proj", "calendar_create", ("Standup",), {},
        {"pending": True, "action_id": "x"},
    )
    assert server.timeline_list("proj") == []


# ------------------------------------------------------------------
# Search tools (FEATURE-SEMANTIC-SEARCH.md)
# ------------------------------------------------------------------


def test_memory_write_is_indexed_and_searchable(wired):
    server.memory_write("proj", "notes/invoice.md", "the invoice is overdue")
    result = server.search_all("invoice")
    assert result["semantic"] is False  # no embedder configured in this fixture
    refs = [r["ref"] for r in result["results"]]
    assert "notes/invoice.md" in refs


def test_backlog_add_is_indexed_and_searchable(wired):
    r = server.backlog_add("proj", "Fix invoice bug", "customers see wrong totals")
    result = server.search_all("invoice")
    hits = [x for x in result["results"] if x["source_type"] == "backlog"]
    assert any(h["ref"] == r["id"] for h in hits)


def test_files_write_is_indexed_and_searchable(wired):
    server.files_write("proj", "/docs/charter.txt", "project charter and scope")
    result = server.search_all("charter")
    refs = [r["ref"] for r in result["results"]]
    assert "/docs/charter.txt" in refs


def test_search_all_hides_files_from_reader(wired, monkeypatch):
    server.files_write("proj", "/secret.txt", "confidential budget numbers")
    monkeypatch.setenv("MEMAIX_USER", "bob")
    result = server.search_all("confidential")
    assert result["results"] == []


def test_search_reindex_requires_owner(wired, monkeypatch):
    monkeypatch.setenv("MEMAIX_USER", "bob")
    with pytest.raises(AccessDenied):
        server.search_reindex("proj")


def test_search_reindex_rebuilds_index(wired):
    server.memory_write("proj", "notes/a.md", "quarterly roadmap")
    result = server.search_reindex("proj")
    assert result["sources"] >= 1
    assert server.search_all("roadmap")["results"]


def test_search_status_reports_embedder_and_counts(wired):
    server.memory_write("proj", "notes/a.md", "content")
    status = server.search_status()
    assert status["semantic_enabled"] is False
    assert status["chunks_by_project"]["proj"] >= 1


def test_failed_write_is_not_indexed(wired, monkeypatch):
    monkeypatch.setenv("MEMAIX_USER", "bob")  # reader — can't write
    with pytest.raises(Exception):
        server.memory_write("proj", "notes/x.md", "hello")
    monkeypatch.setenv("MEMAIX_USER", "alice")
    assert server.search_all("hello")["results"] == []


def test_indexing_hook_failure_does_not_break_the_write(wired, monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("index db is on fire")

    monkeypatch.setattr(server, "_get_search_store", boom)
    result = server.memory_write("proj", "notes/x.md", "hello")
    assert result["path"] == "notes/x.md"  # the actual write still succeeded
