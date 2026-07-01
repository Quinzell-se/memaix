# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the outbox board API routes (FEATURE-APPROVAL-OUTBOX.md).

Auth is bypassed by monkeypatching _require_user directly — cookie-based
board auth itself is exercised elsewhere; this file focuses on the new
outbox routes' ACL/role/idempotency behaviour.
"""

from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from memaix_gateway.acl import Acl
from memaix_gateway.board import routes as board_routes_mod
from memaix_gateway.outbox.queue import ActionQueue


@pytest.fixture()
def rig(tmp_path, monkeypatch):
    acl = Acl(
        users={
            "alice": {"grants": {"proj": "owner"}},
            "bob": {"grants": {"proj": "reader"}},
        },
        projects={"proj": {"vault": str(tmp_path / "vault")}},
    )
    queue = ActionQueue.for_path(tmp_path / "outbox.db")

    monkeypatch.setattr(board_routes_mod, "_acl", lambda: acl)
    monkeypatch.setattr(board_routes_mod, "_outbox", lambda: queue)

    current_user = {"name": "alice"}
    monkeypatch.setattr(board_routes_mod, "_require_user", lambda request: current_user["name"])

    app = Starlette(
        routes=[r for r in board_routes_mod.board_routes if "outbox" in r.path]
    )
    client = TestClient(app)
    return client, queue, current_user


def test_list_outbox_actions(rig):
    client, queue, _ = rig
    queue.enqueue("alice", "proj", "email_send", {"to": "x@y.com"}, "preview")
    resp = client.get("/board/api/outbox?project=proj")
    assert resp.status_code == 200
    assert len(resp.json()["actions"]) == 1


def test_list_filters_by_visible_projects(rig):
    client, queue, _ = rig
    queue.enqueue("alice", "other-proj", "email_send", {}, "p")
    resp = client.get("/board/api/outbox")
    assert resp.json()["actions"] == []


def test_approve_executes_action(rig, monkeypatch):
    client, queue, _ = rig
    aid = queue.enqueue(
        "alice", "proj", "email_send",
        {"to": "x@y.com", "subject": "s", "body": "b", "cc": None}, "p",
    )
    calls = []
    monkeypatch.setattr(
        "memaix_gateway.outbox.execute._default_dispatch",
        lambda: {"email_send": lambda acl, u, p, **kw: calls.append(kw) or {"status": "sent"}},
    )
    resp = client.post(f"/board/api/outbox/{aid}", json={"decision": "approve"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert calls[0]["_confirmed"] is True


def test_reject_never_executes(rig, monkeypatch):
    client, queue, _ = rig
    aid = queue.enqueue("alice", "proj", "email_send", {"to": "x@y.com"}, "p")
    calls = []
    monkeypatch.setattr(
        "memaix_gateway.outbox.execute._default_dispatch",
        lambda: {"email_send": lambda *a, **kw: calls.append(1)},
    )
    resp = client.post(f"/board/api/outbox/{aid}", json={"decision": "reject", "reason": "no"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"
    assert calls == []


def test_reader_cannot_approve_owner_action(rig):
    client, queue, current_user = rig
    aid = queue.enqueue("alice", "proj", "email_send", {"to": "x@y.com"}, "p")
    current_user["name"] = "bob"
    resp = client.post(f"/board/api/outbox/{aid}", json={"decision": "approve"})
    assert resp.status_code == 403


def test_double_approve_is_conflict(rig, monkeypatch):
    client, queue, _ = rig
    aid = queue.enqueue("alice", "proj", "email_send", {"to": "x@y.com"}, "p")
    monkeypatch.setattr(
        "memaix_gateway.outbox.execute._default_dispatch",
        lambda: {"email_send": lambda *a, **kw: {"status": "sent"}},
    )
    first = client.post(f"/board/api/outbox/{aid}", json={"decision": "approve"})
    assert first.status_code == 200
    second = client.post(f"/board/api/outbox/{aid}", json={"decision": "approve"})
    assert second.status_code == 409


def test_invalid_decision_rejected(rig):
    client, queue, _ = rig
    aid = queue.enqueue("alice", "proj", "email_send", {"to": "x@y.com"}, "p")
    resp = client.post(f"/board/api/outbox/{aid}", json={"decision": "maybe"})
    assert resp.status_code == 400


def test_unknown_action_id_404s(rig):
    client, _, _ = rig
    resp = client.post("/board/api/outbox/does-not-exist", json={"decision": "approve"})
    assert resp.status_code == 404
