# SPDX-License-Identifier: AGPL-3.0-or-later
"""Server-level tests for contacts_search/contacts_get — proves the MCP
tools build a ContactsBackend via the connector registry and route through
the shared identity/ACL/audit path (FEATURE-NEXTCLOUD-BACKEND.md §5)."""

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


class _FakeContactsBackend:
    def __init__(self):
        self.searched = []

    def search(self, query):
        self.searched.append(query)
        return [{"id": "anna-uid", "name": "Anna Andersson", "email": "anna@acme.com", "org": "Acme", "phone": ""}]

    def get(self, id):
        if id == "anna-uid":
            return {"id": "anna-uid", "name": "Anna Andersson", "email": "anna@acme.com", "org": "Acme", "phone": ""}
        raise FileNotFoundError(id)


@pytest.fixture()
def wired(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    (vault / "backlog").mkdir(parents=True)
    acl = Acl(
        users={
            "alice": {"grants": {"proj": "owner"}},
            "bob": {"grants": {"proj": "reader"}},
            "carol": {"grants": {}},
        },
        projects={"proj": {"vault": str(vault), "contacts": {"url": "https://nc.example.com/contacts/"}}},
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

    backend = _FakeContactsBackend()
    fake_registry = ConnectorRegistry()
    fake_registry.register(
        ConnectorSpec(type="carddav", capability="contacts", auth="shared", factory=lambda *a: backend)
    )
    monkeypatch.setattr(registry_mod, "_registry", fake_registry)
    return vault, acl, backend


def test_contacts_search_returns_backend_results(wired):
    _vault, _acl, backend = wired
    results = server.contacts_search("proj", "anna")
    assert results[0]["email"] == "anna@acme.com"
    assert backend.searched == ["anna"]


def test_contacts_get_returns_contact(wired):
    result = server.contacts_get("proj", "anna-uid")
    assert result["name"] == "Anna Andersson"


def test_contacts_get_unknown_raises(wired):
    with pytest.raises(FileNotFoundError):
        server.contacts_get("proj", "nope")


def test_contacts_search_records_audit(wired):
    server.contacts_search("proj", "anna")
    tools = [e["tool"] for e in server._get_audit().tail(5)]
    assert "contacts_search" in tools


def test_contacts_search_denies_user_without_project_grant(wired, monkeypatch):
    monkeypatch.setenv("MEMAIX_USER", "carol")
    with pytest.raises(AccessDenied):
        server.contacts_search("proj", "anna")


def test_contacts_search_missing_resource_raises_value_error(wired, monkeypatch):
    monkeypatch.setenv("MEMAIX_USER", "alice")
    acl2 = Acl(users={"alice": {"grants": {"other": "owner"}}}, projects={"other": {"vault": "/tmp/x"}})
    monkeypatch.setattr(server, "_acl", acl2)
    with pytest.raises(ValueError, match="no contacts configured"):
        server.contacts_search("other", "anna")
