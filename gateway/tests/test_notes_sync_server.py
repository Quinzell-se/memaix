# SPDX-License-Identifier: AGPL-3.0-or-later
"""Server-level tests for notes_sync — connector wiring, ACL/audit routing
(FEATURE-NEXTCLOUD-BACKEND.md §7)."""

from __future__ import annotations

import pytest

from memaix_gateway import server
from memaix_gateway.acl import AccessDenied, Acl
from memaix_gateway.outbox.queue import ActionQueue
from memaix_gateway.safety.audit import AuditLog
from memaix_gateway.nextcloud.notes_store import NotesLinkStore
from memaix_gateway.notify.store import NotifyStore
from memaix_gateway.rules.store import RulesStore
from memaix_gateway.search.store import EmbeddingStore
from memaix_gateway.timeline.store import ActionsStore
import memaix_gateway.connectors.registry as registry_mod
from memaix_gateway.connectors.registry import ConnectorRegistry, ConnectorSpec


class _FakeNotes:
    def list_notes(self):
        return [{"id": "1", "title": "Ideas", "content": "brainstorm list", "last_modified": 0}]

    def update_note(self, note_id, *, title=None, content=None):
        return {}


@pytest.fixture()
def wired(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir(parents=True)
    acl = Acl(
        users={
            "alice": {"grants": {"proj": "owner"}},
            "carol": {"grants": {"proj": "collaborator"}},
        },
        projects={"proj": {"vault": str(vault), "notes": {"url": "https://nc.example.com"}}},
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
    monkeypatch.setattr(server, "_notes_link_store", NotesLinkStore.for_path(tmp_path / "notes-link.db"))
    monkeypatch.setenv("MEMAIX_USER", "alice")
    server._rate_limiter._windows.clear()

    fake_registry = ConnectorRegistry()
    fake_registry.register(ConnectorSpec(type="nextcloud", capability="notes", auth="shared", factory=lambda *a: _FakeNotes()))
    monkeypatch.setattr(registry_mod, "_registry", fake_registry)
    return vault, acl


def test_notes_sync_creates_memory_note_from_note(wired):
    result = server.notes_sync("proj")
    assert len(result["created"]) == 1


def test_notes_sync_is_audited(wired):
    server.notes_sync("proj")
    tools = [e["tool"] for e in server._get_audit().tail(5)]
    assert "notes_sync" in tools


def test_notes_sync_requires_owner(wired, monkeypatch):
    monkeypatch.setenv("MEMAIX_USER", "carol")  # collaborator, not owner
    with pytest.raises(AccessDenied):
        server.notes_sync("proj")


def test_notes_sync_missing_resource_raises_value_error(wired, monkeypatch):
    acl2 = Acl(users={"alice": {"grants": {"other": "owner"}}}, projects={"other": {"vault": "/tmp/x"}})
    monkeypatch.setattr(server, "_acl", acl2)
    with pytest.raises(ValueError, match="no notes configured"):
        server.notes_sync("other")
