# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for board card moves being recorded in / undoable via the timeline
(FEATURE-UNDO-TIMELINE.md's 'board_move' inverse)."""

from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from memaix_gateway.acl import Acl
from memaix_gateway.board import routes as board_routes_mod
from memaix_gateway.timeline.store import ActionsStore
from memaix_gateway.timeline.undo import undo
from memaix_gateway.tools import backlog as t_backlog


@pytest.fixture()
def rig(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    (vault / "backlog").mkdir(parents=True)
    acl = Acl(
        users={"alice": {"grants": {"proj": "owner"}}},
        projects={"proj": {"vault": str(vault)}},
    )
    timeline = ActionsStore.for_path(tmp_path / "actions.db")

    monkeypatch.setattr(board_routes_mod, "_acl", lambda: acl)
    monkeypatch.setattr(board_routes_mod, "_timeline", lambda: timeline)
    monkeypatch.setattr(board_routes_mod, "_require_user", lambda request: "alice")

    item = t_backlog.backlog_add(acl, "alice", "proj", "Card title", "desc")

    app = Starlette(
        routes=[r for r in board_routes_mod.board_routes if r.path == "/board/api/item/{id}"]
    )
    client = TestClient(app)
    return client, acl, timeline, item["id"], vault


def test_board_move_is_recorded_in_timeline(rig):
    client, acl, timeline, item_id, vault = rig
    resp = client.patch(f"/board/api/item/{item_id}", json={"project": "proj", "status": "triaged"})
    assert resp.status_code == 200

    entries = timeline.list(["proj"])
    assert len(entries) == 1
    assert entries[0]["tool"] == "board_move"
    assert entries[0]["reversible"] is True
    assert entries[0]["inverse"] == {"tool": "board_move", "args": {"item_id": item_id, "status": "inbox"}}


def test_board_move_undo_restores_previous_status(rig):
    client, acl, timeline, item_id, vault = rig
    client.patch(f"/board/api/item/{item_id}", json={"project": "proj", "status": "triaged"})
    entry_id = timeline.list(["proj"])[0]["id"]

    result = undo(timeline, acl, "alice", entry_id)
    assert result["ok"] is True

    item = t_backlog.backlog_get(acl, "alice", "proj", item_id)
    assert item["status"] == "inbox"


def test_board_move_to_same_status_is_not_recorded(rig):
    client, acl, timeline, item_id, vault = rig
    # inbox -> inbox is a no-op move; nothing meaningful to undo.
    resp = client.patch(f"/board/api/item/{item_id}", json={"project": "proj", "status": "inbox"})
    assert resp.status_code == 200
    assert timeline.list(["proj"]) == []
