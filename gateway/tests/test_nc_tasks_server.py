# SPDX-License-Identifier: AGPL-3.0-or-later
"""Server-level tests for nc_tasks_* — connector wiring, ACL/audit routing
(FEATURE-NEXTCLOUD-BACKEND.md §3, Byggordning step 5)."""

from __future__ import annotations

import pytest

from memaix_gateway import server
from memaix_gateway.acl import AccessDenied, Acl
from memaix_gateway.outbox.queue import ActionQueue
from memaix_gateway.safety.audit import AuditLog
from memaix_gateway.notify.store import NotifyStore
from memaix_gateway.rules.store import RulesStore
from memaix_gateway.search.store import EmbeddingStore
from memaix_gateway.timeline.store import ActionsStore
import memaix_gateway.connectors.registry as registry_mod
from memaix_gateway.connectors.registry import ConnectorRegistry, ConnectorSpec


class _FakeTasksBackend:
    def __init__(self):
        self.tasks = {"t1": {"id": "t1", "title": "Follow up", "due": "", "notes": "", "completed": False}}

    def list(self):
        return list(self.tasks.values())

    def add(self, title, due=None, notes=None):
        task = {"id": "new-id", "title": title, "due": due or "", "notes": notes or "", "completed": False}
        self.tasks["new-id"] = task
        return task

    def complete(self, id):
        if id not in self.tasks:
            raise FileNotFoundError(id)
        self.tasks[id]["completed"] = True
        return self.tasks[id]


@pytest.fixture()
def wired(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    (vault / "backlog").mkdir(parents=True)
    acl = Acl(
        users={
            "alice": {"grants": {"proj": "owner"}},
            "bob": {"grants": {"proj": "reader"}},
        },
        projects={"proj": {"vault": str(vault), "tasks": {"url": "https://nc.example.com/tasks/"}}},
    )
    AuditLog._clear_instances()
    monkeypatch.setattr(server, "_acl", acl)
    monkeypatch.setattr(server, "_audit", AuditLog.for_path(tmp_path / "audit.db"))
    monkeypatch.setattr(server, "_outbox_queue", ActionQueue.for_path(tmp_path / "outbox.db"))
    monkeypatch.setattr(server, "_timeline_store", ActionsStore.for_path(tmp_path / "actions.db"))
    monkeypatch.setattr(server, "_search_store", EmbeddingStore.for_path(tmp_path / "index.db"))
    monkeypatch.setattr(server, "_search_embedder", None)
    monkeypatch.setattr(server, "_search_embedder_loaded", True)
    monkeypatch.setattr(server, "_notify_store", NotifyStore.for_path(tmp_path / "notify.db"))
    monkeypatch.setattr(server, "_rules_store", RulesStore.for_path(tmp_path / "rules.db"))
    monkeypatch.setenv("MEMAIX_USER", "alice")
    server._rate_limiter._windows.clear()

    backend = _FakeTasksBackend()
    fake_registry = ConnectorRegistry()
    fake_registry.register(ConnectorSpec(type="caldav", capability="tasks", auth="shared", factory=lambda *a: backend))
    monkeypatch.setattr(registry_mod, "_registry", fake_registry)
    return vault, acl, backend


def test_nc_tasks_list(wired):
    tasks = server.nc_tasks_list("proj")
    assert tasks[0]["title"] == "Follow up"


def test_nc_tasks_add(wired):
    result = server.nc_tasks_add("proj", "Call supplier", "2025-03-01", "ask pricing")
    assert result["title"] == "Call supplier"


def test_nc_tasks_complete(wired, monkeypatch):
    monkeypatch.setenv("MEMAIX_USER", "alice")
    result = server.nc_tasks_complete("proj", "t1")
    assert result["completed"] is True


def test_nc_tasks_complete_unknown_raises(wired):
    with pytest.raises(FileNotFoundError):
        server.nc_tasks_complete("proj", "nope")


def test_nc_tasks_reader_can_list_but_not_add(wired, monkeypatch):
    monkeypatch.setenv("MEMAIX_USER", "bob")
    assert server.nc_tasks_list("proj") != []
    with pytest.raises(AccessDenied):
        server.nc_tasks_add("proj", "New task")


def test_nc_tasks_add_is_audited(wired):
    server.nc_tasks_add("proj", "Call supplier")
    tools = [e["tool"] for e in server._get_audit().tail(5)]
    assert "nc_tasks_add" in tools


def test_nc_tasks_missing_resource_raises_value_error(wired, monkeypatch):
    acl2 = Acl(users={"alice": {"grants": {"other": "owner"}}}, projects={"other": {"vault": "/tmp/x"}})
    monkeypatch.setattr(server, "_acl", acl2)
    with pytest.raises(ValueError, match="no tasks configured"):
        server.nc_tasks_list("other")
