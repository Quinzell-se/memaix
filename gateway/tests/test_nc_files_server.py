# SPDX-License-Identifier: AGPL-3.0-or-later
"""Server-level tests for nc_files_* — connector wiring, ACL/audit routing,
and the search-indexing hook (FEATURE-NEXTCLOUD-BACKEND.md §4)."""

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


class _FakeFilesBackend:
    def __init__(self):
        self.files = {"notes.txt": "hello there"}

    def list_files(self, path):
        return [{"name": "notes.txt", "type": "file", "size": len(self.files["notes.txt"])}]

    def read_file(self, path):
        return self.files[path.strip("/")]

    def write_file(self, path, content):
        self.files[path.strip("/")] = content
        return f"ok: {path}"

    def search_files(self, query, path):
        return [{"path": "/notes.txt", "matches": [{"line": 1, "text": self.files["notes.txt"]}]}] if query in self.files["notes.txt"] else []


@pytest.fixture()
def wired(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    (vault / "backlog").mkdir(parents=True)
    acl = Acl(
        users={
            "alice": {"grants": {"proj": "owner"}},
            "bob": {"grants": {"proj": "reader"}},
        },
        projects={"proj": {"vault": str(vault), "files": {"url": "https://nc.example.com/files/"}}},
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

    backend = _FakeFilesBackend()
    fake_registry = ConnectorRegistry()
    fake_registry.register(
        ConnectorSpec(type="webdav", capability="files", auth="shared", factory=lambda *a: backend)
    )
    monkeypatch.setattr(registry_mod, "_registry", fake_registry)
    return vault, acl, backend


def test_nc_files_list(wired):
    entries = server.nc_files_list("proj")
    assert entries[0]["name"] == "notes.txt"


def test_nc_files_read(wired):
    assert server.nc_files_read("proj", "notes.txt") == "hello there"


def test_nc_files_write_updates_backend(wired):
    server.nc_files_write("proj", "notes.txt", "updated")
    assert server.nc_files_read("proj", "notes.txt") == "updated"


def test_nc_files_search(wired):
    results = server.nc_files_search("proj", "hello")
    assert results[0]["path"] == "/notes.txt"


def test_nc_files_write_is_audited(wired):
    server.nc_files_write("proj", "notes.txt", "updated")
    tools = [e["tool"] for e in server._get_audit().tail(5)]
    assert "nc_files_write" in tools


def test_nc_files_write_is_indexed_and_searchable(wired):
    server.nc_files_write("proj", "reports/status.txt", "the acme project charter is on track")
    result = server.search_all("charter")
    hits = [r for r in result["results"] if r["source_type"] == "nc_file"]
    assert any(h["ref"] == "reports/status.txt" for h in hits)


def test_nc_files_reader_cannot_write(wired, monkeypatch):
    monkeypatch.setenv("MEMAIX_USER", "bob")
    with pytest.raises(AccessDenied):
        server.nc_files_write("proj", "notes.txt", "hacked")


def test_nc_files_missing_resource_raises_value_error(wired, monkeypatch):
    acl2 = Acl(users={"alice": {"grants": {"other": "owner"}}}, projects={"other": {"vault": "/tmp/x"}})
    monkeypatch.setattr(server, "_acl", acl2)
    with pytest.raises(ValueError, match="no files configured"):
        server.nc_files_list("other")
