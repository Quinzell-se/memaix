# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for nextcloud.sync.notes_sync — the Notes <-> memory two-way sync
algorithm (FEATURE-NEXTCLOUD-BACKEND.md §7)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from memaix_gateway.acl import Acl, AccessDenied
from memaix_gateway.nextcloud.notes_store import NotesLinkStore
from memaix_gateway.nextcloud.sync import notes_sync
from memaix_gateway.tools import memory as t_memory

BASELINE = datetime(2025, 1, 1, tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _epoch(dt: datetime) -> float:
    return dt.timestamp()


class _FakeNotes:
    def __init__(self, notes=None):
        self.notes = notes or {}
        self.updates = []

    def list_notes(self):
        return list(self.notes.values())

    def get_note(self, note_id):
        return self.notes[note_id]

    def update_note(self, note_id, *, title=None, content=None):
        self.updates.append((note_id, title, content))
        note = self.notes[note_id]
        if title is not None:
            note["title"] = title
        if content is not None:
            note["content"] = content
        return note


@pytest.fixture()
def acl(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir(parents=True)
    return Acl(users={"alice": {"grants": {"proj": "owner"}}}, projects={"proj": {"vault": str(vault)}})


@pytest.fixture()
def link_store(tmp_path):
    return NotesLinkStore.for_path(tmp_path / "links.db")


def _linked_note(acl, link_store, path="notes/ideas.md", content="brainstorm list", nc_id="1", synced_at=None):
    baseline = synced_at if synced_at is not None else _iso(BASELINE)
    t_memory.memory_write(acl, "alice", "proj", path, content)
    # Pin the memory store's own updated_at to the same controlled baseline.
    store = t_memory._get_store(acl, "proj")
    store._conn.execute("UPDATE notes SET updated_at=? WHERE path=?", (baseline, path))
    store._conn.commit()
    link_store.set_link("proj", path, nc_id, baseline)
    return path


def test_new_note_is_pulled_into_memory(acl, link_store):
    notes = _FakeNotes({"1": {"id": "1", "title": "Ideas", "content": "brainstorm list", "last_modified": 1000}})
    result = notes_sync(acl, "alice", "proj", _notes=notes, link_store=link_store)

    assert len(result["created"]) == 1
    note_path = result["created"][0]["note_path"]
    assert t_memory.memory_read(acl, "alice", "proj", note_path)["content"] == "brainstorm list"


def test_new_note_title_is_slugified_into_path(acl, link_store):
    notes = _FakeNotes({"1": {"id": "1", "title": "Meeting Notes!!", "content": "x", "last_modified": 1000}})
    result = notes_sync(acl, "alice", "proj", _notes=notes, link_store=link_store)
    assert result["created"][0]["note_path"] == "notes/meeting-notes.md"


def test_second_sync_does_not_recreate_linked_note(acl, link_store):
    notes = _FakeNotes({"1": {"id": "1", "title": "Ideas", "content": "x", "last_modified": 1000}})
    notes_sync(acl, "alice", "proj", _notes=notes, link_store=link_store)
    result = notes_sync(acl, "alice", "proj", _notes=notes, link_store=link_store)
    assert result["created"] == []


def test_notes_only_change_updates_memory(acl, link_store):
    path = _linked_note(acl, link_store, synced_at=_iso(BASELINE))
    notes = _FakeNotes({"1": {"id": "1", "title": "Ideas", "content": "updated from nextcloud",
                               "last_modified": _epoch(BASELINE + timedelta(days=1))}})

    result = notes_sync(acl, "alice", "proj", _notes=notes, link_store=link_store)

    assert path in result["updated_from_notes"]
    assert t_memory.memory_read(acl, "alice", "proj", path)["content"] == "updated from nextcloud"


def test_memory_only_change_updates_notes(acl, link_store):
    path = _linked_note(acl, link_store, synced_at=_iso(BASELINE))
    notes = _FakeNotes({"1": {"id": "1", "title": "Ideas", "content": "brainstorm list", "last_modified": 0}})

    t_memory.memory_write(acl, "alice", "proj", path, "updated from memaix")
    store = t_memory._get_store(acl, "proj")
    store._conn.execute("UPDATE notes SET updated_at=? WHERE path=?", (_iso(BASELINE + timedelta(days=1)), path))
    store._conn.commit()

    result = notes_sync(acl, "alice", "proj", _notes=notes, link_store=link_store)

    assert path in result["updated_from_memory"]
    assert notes.updates and notes.updates[0][2] == "updated from memaix"


def test_no_change_is_a_noop(acl, link_store):
    _linked_note(acl, link_store)
    notes = _FakeNotes({"1": {"id": "1", "title": "Ideas", "content": "brainstorm list", "last_modified": 0}})
    result = notes_sync(acl, "alice", "proj", _notes=notes, link_store=link_store)
    assert result["updated_from_notes"] == []
    assert result["updated_from_memory"] == []
    assert result["conflicts"] == []


def test_both_changed_is_a_conflict_and_newer_wins(acl, link_store):
    path = _linked_note(acl, link_store, synced_at=_iso(BASELINE))
    notes = _FakeNotes({"1": {"id": "1", "title": "Ideas", "content": "from nextcloud",
                               "last_modified": _epoch(BASELINE + timedelta(days=150))}})
    t_memory.memory_write(acl, "alice", "proj", path, "from memaix")
    store = t_memory._get_store(acl, "proj")
    store._conn.execute("UPDATE notes SET updated_at=? WHERE path=?", (_iso(BASELINE + timedelta(days=14)), path))
    store._conn.commit()

    result = notes_sync(acl, "alice", "proj", _notes=notes, link_store=link_store)

    assert len(result["conflicts"]) == 1
    assert result["conflicts"][0]["winner"] == "notes"
    assert t_memory.memory_read(acl, "alice", "proj", path)["content"] == "from nextcloud"


def test_deleted_note_is_skipped_not_deleted(acl, link_store):
    path = _linked_note(acl, link_store)
    notes = _FakeNotes({})  # note no longer exists on the Nextcloud side
    result = notes_sync(acl, "alice", "proj", _notes=notes, link_store=link_store)
    assert result == {"created": [], "updated_from_notes": [], "updated_from_memory": [], "conflicts": []}
    assert t_memory.memory_read(acl, "alice", "proj", path)["content"]  # still exists


def test_reader_cannot_sync(acl, link_store):
    acl2 = Acl(users={"bob": {"grants": {"proj": "reader"}}}, projects=acl.projects)
    notes = _FakeNotes({})
    with pytest.raises(AccessDenied):
        notes_sync(acl2, "bob", "proj", _notes=notes, link_store=link_store)
