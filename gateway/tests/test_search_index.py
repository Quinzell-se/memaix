# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for search.index — chunking, upsert/delete, reindex."""

from __future__ import annotations

import pytest

from memaix_gateway.acl import Acl
from memaix_gateway.search.embedder import FakeEmbedder
from memaix_gateway.search.index import chunk_text, index_delete, index_upsert, reindex_project
from memaix_gateway.search.store import EmbeddingStore
from memaix_gateway.tools import backlog as t_backlog
from memaix_gateway.tools import memory as t_memory


def test_chunk_text_short_text_single_chunk():
    assert chunk_text("hello world", size=800) == ["hello world"]


def test_chunk_text_empty_returns_nothing():
    assert chunk_text("") == []
    assert chunk_text("   \n  ") == []


def test_chunk_text_splits_long_text():
    text = "line\n" * 500  # 2500 chars
    chunks = chunk_text(text, size=200, overlap=20)
    assert len(chunks) > 1
    assert all(len(c) <= 220 for c in chunks)  # some slack for the newline-aligned break


def test_chunk_text_makes_progress_even_without_newlines():
    text = "x" * 5000  # no newlines at all
    chunks = chunk_text(text, size=200, overlap=190)
    assert len(chunks) > 1
    assert len(chunks) < 5000  # must terminate, not loop forever


@pytest.fixture()
def store(tmp_path):
    return EmbeddingStore.for_path(tmp_path / "index.db")


@pytest.fixture()
def embedder():
    return FakeEmbedder(dim=32)


def test_index_upsert_creates_searchable_chunks(store, embedder):
    n = index_upsert(store, embedder, "proj", "memory", "note.md", "note.md", "invoice is overdue")
    assert n == 1
    hits = store.fts_search(["proj"], ["memory"], "invoice", 10)
    assert len(hits) == 1


def test_index_upsert_empty_text_deletes_existing(store, embedder):
    index_upsert(store, embedder, "proj", "memory", "note.md", "note.md", "content")
    n = index_upsert(store, embedder, "proj", "memory", "note.md", "note.md", "")
    assert n == 0
    assert store.fts_search(["proj"], ["memory"], "content", 10) == []


def test_index_delete(store, embedder):
    index_upsert(store, embedder, "proj", "memory", "note.md", "note.md", "content")
    index_delete(store, "proj", "memory", "note.md")
    assert store.candidates(["proj"], ["memory"], 10) == []


def test_index_upsert_without_embedder_still_lexically_searchable(store):
    n = index_upsert(store, None, "proj", "memory", "note.md", "note.md", "invoice overdue")
    assert n == 1
    assert store.candidates(["proj"], ["memory"], 10) == []  # no vectors
    assert len(store.fts_search(["proj"], ["memory"], "invoice", 10)) == 1


@pytest.fixture()
def vault(tmp_path):
    v = tmp_path / "vault"
    (v / "memory").mkdir(parents=True)
    (v / "backlog").mkdir(parents=True)
    (v / "memory" / "standup.md").write_text("Yesterday we discussed the invoice delay.")
    (v / "docs.txt").write_text("Project charter and scope document.")
    return v


@pytest.fixture()
def acl(vault):
    return Acl(users={"alice": {"grants": {"proj": "owner"}}}, projects={"proj": {"vault": str(vault)}})


def test_reindex_project_indexes_memory_backlog_and_files(store, embedder, acl, vault):
    t_backlog.backlog_add(acl, "alice", "proj", "Fix the invoice bug", "long description here")
    result = reindex_project(store, embedder, acl, "proj")
    assert result["sources"] >= 3  # standup.md + docs.txt + 1 backlog item
    assert result["chunks"] >= 3

    hits = store.fts_search(["proj"], ["memory"], "invoice", 10)
    assert len(hits) == 1
    hits = store.fts_search(["proj"], ["backlog"], "invoice", 10)
    assert len(hits) == 1
    hits = store.fts_search(["proj"], ["file"], "charter", 10)
    assert len(hits) == 1


def test_reindex_project_skips_internal_files(store, embedder, acl, vault):
    system_dir = vault / "_system"
    system_dir.mkdir(exist_ok=True)
    (system_dir / "onboarding.json").write_text('{"secret": "should-not-be-indexed"}')
    reindex_project(store, embedder, acl, "proj")
    hits = store.fts_search(["proj"], ["file"], "should", 10)
    assert hits == []


def test_reindex_project_no_vault_raises(tmp_path, acl):
    acl2 = Acl(users={"alice": {"grants": {"x": "owner"}}}, projects={"x": {}})
    with pytest.raises(ValueError):
        reindex_project(EmbeddingStore.for_path(tmp_path / "never.db"), None, acl2, "x")
