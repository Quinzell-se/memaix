# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for timeline.undo.undo."""

from __future__ import annotations

import pytest

from memaix_gateway.acl import Acl, AccessDenied
from memaix_gateway.timeline.store import ActionsStore
from memaix_gateway.timeline.undo import undo


@pytest.fixture()
def store(tmp_path):
    return ActionsStore.for_path(tmp_path / "actions.db")


@pytest.fixture()
def acl():
    return Acl(
        users={
            "alice": {"grants": {"proj": "owner"}},
            "carol": {"grants": {"proj": "collaborator"}},
            "bob": {"grants": {"proj": "reader"}},
        },
        projects={"proj": {"vault": "/v"}},
    )


def test_undo_calls_inverse_tool(store, acl):
    aid = store.record(
        "carol", "proj", "calendar_create", 'Skapade "Standup"',
        {"tool": "calendar_delete", "args": {"id": "ev-1"}},
    )
    calls = []

    def fake_delete(acl_, user, project, **kwargs):
        calls.append((user, project, kwargs))
        return {"deleted": True}

    result = undo(store, acl, "carol", aid, tools={"calendar_delete": fake_delete})
    assert result["ok"] is True
    assert calls[0] == ("carol", "proj", {"id": "ev-1"})
    assert store.get(aid)["status"] == "undone"


def test_undo_is_idempotent_second_call_refuses(store, acl):
    aid = store.record(
        "carol", "proj", "calendar_create", "x", {"tool": "calendar_delete", "args": {"id": "e"}}
    )
    tools = {"calendar_delete": lambda *a, **kw: {"deleted": True}}
    first = undo(store, acl, "carol", aid, tools=tools)
    assert first["ok"] is True
    second = undo(store, acl, "carol", aid, tools=tools)
    assert second["ok"] is False
    assert "undone" in second["error"]


def test_undo_irreversible_action_returns_error(store, acl):
    aid = store.record("carol", "proj", "email_send", "sent", None)
    result = undo(store, acl, "carol", aid)
    assert result == {"ok": False, "error": "irreversible", "action_id": aid}
    assert store.get(aid)["status"] == "done"


def test_undo_missing_action_raises(store, acl):
    with pytest.raises(FileNotFoundError):
        undo(store, acl, "carol", "nope")


def test_undo_requires_original_role(store, acl):
    aid = store.record(
        "carol", "proj", "backlog_add", "x",
        {"tool": "backlog_set_status", "args": {"id": "i1", "status": "rejected", "expected_version": 1}},
    )
    with pytest.raises(AccessDenied):
        undo(store, acl, "bob", aid)  # bob is only a reader; backlog_add needed collaborator
    assert store.get(aid)["status"] == "done"


def test_undo_handles_optimistic_lock_conflict(store, acl):
    aid = store.record(
        "carol", "proj", "backlog_add", "x",
        {"tool": "backlog_set_status", "args": {"id": "i1", "status": "rejected", "expected_version": 1}},
    )

    def conflicting_set_status(acl_, user, project, **kwargs):
        return {"conflict": True, "current_version": 2}

    result = undo(store, acl, "carol", aid, tools={"backlog_set_status": conflicting_set_status})
    assert result["ok"] is False
    assert "conflict" in result["error"]
    assert store.get(aid)["status"] == "undo_failed"


def test_undo_exception_marks_undo_failed(store, acl):
    aid = store.record(
        "carol", "proj", "calendar_create", "x", {"tool": "calendar_delete", "args": {"id": "e"}}
    )

    def boom(*a, **kw):
        raise RuntimeError("caldav unreachable")

    result = undo(store, acl, "carol", aid, tools={"calendar_delete": boom})
    assert result["ok"] is False
    assert result["error"] == "caldav unreachable"
    assert store.get(aid)["status"] == "undo_failed"


def test_undo_records_undo_action_linked_to_original(store, acl):
    aid = store.record(
        "carol", "proj", "memory_write", "wrote note",
        {"tool": "memory_revert", "args": {"commit": "abc"}},
    )
    result = undo(store, acl, "carol", aid, tools={"memory_revert": lambda *a, **kw: {"new_commit": "xyz"}})
    undo_id = result["undo_action_id"]
    assert store.get(aid)["undo_action_id"] == undo_id
    assert store.get(undo_id)["undo_of"] == aid
    assert store.get(undo_id)["reversible"] is False  # the undo itself isn't undoable in v1


def test_undo_no_executor_for_inverse_tool(store, acl):
    aid = store.record("carol", "proj", "calendar_create", "x", {"tool": "unknown_tool", "args": {}})
    result = undo(store, acl, "carol", aid, tools={})
    assert result["ok"] is False
    assert "no undo executor" in result["error"]
    assert store.get(aid)["status"] == "undo_failed"
