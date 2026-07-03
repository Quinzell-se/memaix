# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for nextcloud.sync.deck_sync — the Deck <-> backlog two-way sync
algorithm (FEATURE-NEXTCLOUD-BACKEND.md §7)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from memaix_gateway import frontmatter as fm
from memaix_gateway.acl import Acl
from memaix_gateway.nextcloud.sync import deck_sync
from memaix_gateway.tools import backlog as t_backlog

BASELINE = datetime(2025, 1, 1, tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _epoch(dt: datetime) -> float:
    return dt.timestamp()


class _FakeDeck:
    def __init__(self, cards=None):
        self.cards = cards or {}
        self.updates = []

    def list_cards(self, board_id, stack_id):
        return list(self.cards.values())

    def get_card(self, board_id, stack_id, card_id):
        return self.cards[card_id]

    def update_card(self, board_id, stack_id, card_id, *, title=None, description=None):
        self.updates.append((card_id, title, description))
        card = self.cards[card_id]
        if title is not None:
            card["title"] = title
        if description is not None:
            card["description"] = description
        return card


@pytest.fixture()
def acl(tmp_path):
    vault = tmp_path / "vault"
    (vault / "backlog").mkdir(parents=True)
    return Acl(users={"alice": {"grants": {"proj": "owner"}}}, projects={"proj": {"vault": str(vault)}})


def _linked_item(acl, title="Follow up", description="call the client", card_id="1", synced_at=None):
    """Create a backlog item already linked to a Deck card, with both
    `updated_at` and `deck_synced_at` pinned to `synced_at` (default
    BASELINE) — a fully controlled starting point, since backlog_add()
    otherwise stamps `updated_at` to the real wall-clock time."""
    baseline = synced_at if synced_at is not None else _iso(BASELINE)
    result = t_backlog.backlog_add(acl, "alice", "proj", title, description)
    path = Path(acl.resource("proj", "vault")) / "backlog" / f"{result['id']}.md"
    meta, body = fm.split(path.read_text())
    meta.update({"deck_board_id": 1, "deck_stack_id": 2, "deck_card_id": card_id, "updated_at": baseline, "deck_synced_at": baseline})
    fm.write_atomic(path, fm.join(meta, body))
    return result["id"]


def _set_item_fields(acl, item_id: str, **fields) -> None:
    path = Path(acl.resource("proj", "vault")) / "backlog" / f"{item_id}.md"
    meta, body = fm.split(path.read_text())
    meta.update(fields)
    fm.write_atomic(path, fm.join(meta, body))


def test_new_card_creates_backlog_item(acl):
    deck = _FakeDeck({"1": {"id": "1", "title": "Follow up", "description": "call the client", "last_modified": 1000}})
    result = deck_sync(acl, "alice", "proj", _deck=deck, board_id=1, stack_id=2)

    assert len(result["created"]) == 1
    items = t_backlog.backlog_list(acl, "alice", "proj")
    assert items[0]["title"] == "Follow up"
    assert items[0]["deck_card_id"] == "1"


def test_second_sync_does_not_recreate_linked_item(acl):
    deck = _FakeDeck({"1": {"id": "1", "title": "Follow up", "description": "x", "last_modified": 1000}})
    deck_sync(acl, "alice", "proj", _deck=deck, board_id=1, stack_id=2)
    result = deck_sync(acl, "alice", "proj", _deck=deck, board_id=1, stack_id=2)
    assert result["created"] == []
    assert len(t_backlog.backlog_list(acl, "alice", "proj")) == 1


def test_deck_only_change_updates_backlog(acl):
    item_id = _linked_item(acl, synced_at=_iso(BASELINE))
    deck = _FakeDeck({
        "1": {"id": "1", "title": "Follow up URGENTLY", "description": "call now",
              "last_modified": _epoch(BASELINE + timedelta(days=1))},
    })

    result = deck_sync(acl, "alice", "proj", _deck=deck, board_id=1, stack_id=2)

    assert item_id in result["updated_from_deck"]
    item = t_backlog.backlog_get(acl, "alice", "proj", item_id)
    assert item["title"] == "Follow up URGENTLY"
    assert item["description"] == "call now"


def test_backlog_only_change_updates_deck(acl):
    item_id = _linked_item(acl, synced_at=_iso(BASELINE))
    deck = _FakeDeck({
        "1": {"id": "1", "title": "Follow up", "description": "call the client", "last_modified": 0},
    })

    # Simulate a backlog-side edit after the sync baseline.
    _set_item_fields(acl, item_id, updated_at=_iso(BASELINE + timedelta(days=1)))

    result = deck_sync(acl, "alice", "proj", _deck=deck, board_id=1, stack_id=2)

    assert item_id in result["updated_from_backlog"]
    assert deck.updates  # update_card was called


def test_no_change_is_a_noop(acl):
    _linked_item(acl)
    deck = _FakeDeck({"1": {"id": "1", "title": "Follow up", "description": "call the client", "last_modified": 0}})
    result = deck_sync(acl, "alice", "proj", _deck=deck, board_id=1, stack_id=2)
    assert result["updated_from_deck"] == []
    assert result["updated_from_backlog"] == []
    assert result["conflicts"] == []


def test_both_sides_changed_is_a_conflict_and_newer_wins(acl):
    item_id = _linked_item(acl, synced_at=_iso(BASELINE))
    # Deck side changed most recently (baseline + 5 months).
    deck = _FakeDeck({
        "1": {"id": "1", "title": "Deck version", "description": "from deck",
              "last_modified": _epoch(BASELINE + timedelta(days=150))},
    })
    # Backlog side also changed, but less recently (baseline + 2 weeks).
    _set_item_fields(acl, item_id, updated_at=_iso(BASELINE + timedelta(days=14)), title="Backlog version")

    result = deck_sync(acl, "alice", "proj", _deck=deck, board_id=1, stack_id=2)

    assert len(result["conflicts"]) == 1
    assert result["conflicts"][0]["winner"] == "deck"
    item = t_backlog.backlog_get(acl, "alice", "proj", item_id)
    assert item["title"] == "Deck version"


def test_both_sides_changed_backlog_newer_wins(acl):
    item_id = _linked_item(acl, synced_at=_iso(BASELINE))
    deck = _FakeDeck({
        "1": {"id": "1", "title": "Deck version", "description": "from deck",
              "last_modified": _epoch(BASELINE + timedelta(days=2))},
    })
    _set_item_fields(acl, item_id, updated_at=_iso(BASELINE + timedelta(days=150)), title="Backlog version")

    result = deck_sync(acl, "alice", "proj", _deck=deck, board_id=1, stack_id=2)

    assert result["conflicts"][0]["winner"] == "backlog"
    assert deck.updates and deck.updates[0][1] == "Backlog version"


def test_deleted_card_is_skipped_not_deleted(acl):
    item_id = _linked_item(acl)
    deck = _FakeDeck({})  # card no longer exists on the Deck side
    result = deck_sync(acl, "alice", "proj", _deck=deck, board_id=1, stack_id=2)
    assert result == {"created": [], "updated_from_deck": [], "updated_from_backlog": [], "conflicts": []}
    # backlog item must still exist
    assert t_backlog.backlog_get(acl, "alice", "proj", item_id)


def test_reader_cannot_sync(acl):
    acl2 = Acl(users={"bob": {"grants": {"proj": "reader"}}}, projects=acl.projects)
    deck = _FakeDeck({})
    from memaix_gateway.acl import AccessDenied

    with pytest.raises(AccessDenied):
        deck_sync(acl2, "bob", "proj", _deck=deck, board_id=1, stack_id=2)
