# SPDX-License-Identifier: AGPL-3.0-or-later
"""Server-level tests for deck_sync — connector + resource-config wiring,
ACL/audit routing (FEATURE-NEXTCLOUD-BACKEND.md §7)."""

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


class _FakeDeck:
    def list_cards(self, board_id, stack_id):
        assert board_id == 10 and stack_id == 20
        return [{"id": "1", "title": "Follow up", "description": "call the client", "last_modified": 0}]

    def update_card(self, board_id, stack_id, card_id, *, title=None, description=None):
        return {}


@pytest.fixture()
def wired(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    (vault / "backlog").mkdir(parents=True)
    acl = Acl(
        users={
            "alice": {"grants": {"proj": "owner"}},
            "carol": {"grants": {"proj": "collaborator"}},
        },
        projects={"proj": {"vault": str(vault), "deck": {"url": "https://nc.example.com", "board_id": 10, "stack_id": 20}}},
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

    fake_registry = ConnectorRegistry()
    fake_registry.register(ConnectorSpec(type="nextcloud", capability="deck", auth="shared", factory=lambda *a: _FakeDeck()))
    monkeypatch.setattr(registry_mod, "_registry", fake_registry)
    return vault, acl


def test_deck_sync_creates_backlog_item_from_card(wired):
    result = server.deck_sync("proj")
    assert len(result["created"]) == 1


def test_deck_sync_passes_board_and_stack_ids_from_resource_config(wired):
    # _FakeDeck.list_cards asserts board_id=10, stack_id=20 — a mismatch
    # would raise inside the fake, failing this test.
    server.deck_sync("proj")


def test_deck_sync_is_audited(wired):
    server.deck_sync("proj")
    tools = [e["tool"] for e in server._get_audit().tail(5)]
    assert "deck_sync" in tools


def test_deck_sync_requires_owner(wired, monkeypatch):
    monkeypatch.setenv("MEMAIX_USER", "carol")  # collaborator, not owner
    with pytest.raises(AccessDenied):
        server.deck_sync("proj")


def test_deck_sync_missing_resource_raises_value_error(wired, monkeypatch):
    acl2 = Acl(users={"alice": {"grants": {"other": "owner"}}}, projects={"other": {"vault": "/tmp/x"}})
    monkeypatch.setattr(server, "_acl", acl2)
    with pytest.raises(ValueError, match="no deck configured"):
        server.deck_sync("other")
