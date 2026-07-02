# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for nextcloud.notes_store.NotesLinkStore."""

from __future__ import annotations

import pytest

from memaix_gateway.nextcloud.notes_store import NotesLinkStore


@pytest.fixture()
def store(tmp_path):
    return NotesLinkStore.for_path(tmp_path / "links.db")


def test_set_and_list_links(store):
    store.set_link("proj", "notes/ideas.md", "1", "2025-01-01T00:00:00+00:00")
    links = store.list_links("proj")
    assert links == [
        {"project": "proj", "note_path": "notes/ideas.md", "nc_note_id": "1", "synced_at": "2025-01-01T00:00:00+00:00"}
    ]


def test_links_are_project_scoped(store):
    store.set_link("proj", "notes/ideas.md", "1", "2025-01-01T00:00:00+00:00")
    store.set_link("other", "notes/ideas.md", "1", "2025-01-01T00:00:00+00:00")
    assert len(store.list_links("proj")) == 1
    assert len(store.list_links("other")) == 1


def test_set_link_upserts_existing_path(store):
    store.set_link("proj", "notes/ideas.md", "1", "2025-01-01T00:00:00+00:00")
    store.set_link("proj", "notes/ideas.md", "1", "2025-02-01T00:00:00+00:00")
    links = store.list_links("proj")
    assert len(links) == 1
    assert links[0]["synced_at"] == "2025-02-01T00:00:00+00:00"


def test_list_links_empty_project(store):
    assert store.list_links("nonexistent") == []
