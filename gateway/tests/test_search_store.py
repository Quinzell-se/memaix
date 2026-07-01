# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for search.store.EmbeddingStore."""

from __future__ import annotations

import pytest

from memaix_gateway.search.store import EmbeddingStore


@pytest.fixture()
def store(tmp_path):
    return EmbeddingStore.for_path(tmp_path / "index.db")


def test_replace_chunks_and_candidates_roundtrip(store):
    store.replace_chunks("proj", "memory", "note.md", [
        {"chunk_ix": 0, "title": "note.md", "text": "hello world", "vector": [0.1, 0.2, 0.3]},
    ])
    cands = store.candidates(["proj"], ["memory"], 10)
    assert len(cands) == 1
    assert list(cands[0]["vector"]) == pytest.approx([0.1, 0.2, 0.3], abs=1e-5)


def test_replace_chunks_removes_old_chunks(store):
    store.replace_chunks("proj", "memory", "note.md", [
        {"chunk_ix": 0, "title": "t", "text": "one", "vector": [1.0]},
        {"chunk_ix": 1, "title": "t", "text": "two", "vector": [1.0]},
    ])
    store.replace_chunks("proj", "memory", "note.md", [
        {"chunk_ix": 0, "title": "t", "text": "only one now", "vector": [1.0]},
    ])
    cands = store.candidates(["proj"], ["memory"], 10)
    assert len(cands) == 1
    assert cands[0]["text"] == "only one now"


def test_fts_search_finds_by_word(store):
    store.replace_chunks("proj", "memory", "a.md", [
        {"chunk_ix": 0, "title": "a", "text": "the invoice is overdue", "vector": None},
    ])
    hits = store.fts_search(["proj"], ["memory"], "invoice", 10)
    assert len(hits) == 1
    assert hits[0]["ref"] == "a.md"


def test_fts_search_scoped_by_project(store):
    store.replace_chunks("proj-a", "memory", "a.md", [
        {"chunk_ix": 0, "title": "a", "text": "budget planning", "vector": None},
    ])
    store.replace_chunks("proj-b", "memory", "b.md", [
        {"chunk_ix": 0, "title": "b", "text": "budget review", "vector": None},
    ])
    hits = store.fts_search(["proj-a"], ["memory"], "budget", 10)
    assert len(hits) == 1
    assert hits[0]["project"] == "proj-a"


def test_delete_removes_chunks(store):
    store.replace_chunks("proj", "memory", "a.md", [
        {"chunk_ix": 0, "title": "a", "text": "content", "vector": [1.0]},
    ])
    store.delete("proj", "memory", "a.md")
    assert store.candidates(["proj"], ["memory"], 10) == []
    assert store.fts_search(["proj"], ["memory"], "content", 10) == []


def test_count_by_project(store):
    store.replace_chunks("proj-a", "memory", "a.md", [
        {"chunk_ix": 0, "title": "a", "text": "x", "vector": [1.0]},
        {"chunk_ix": 1, "title": "a", "text": "y", "vector": [1.0]},
    ])
    counts = store.count_by_project(["proj-a", "proj-b"])
    assert counts == {"proj-a": 2, "proj-b": 0}


def test_candidates_empty_inputs(store):
    assert store.candidates([], ["memory"], 10) == []
    assert store.candidates(["proj"], [], 10) == []


def test_vector_none_excluded_from_candidates(store):
    store.replace_chunks("proj", "memory", "a.md", [
        {"chunk_ix": 0, "title": "a", "text": "no vector here", "vector": None},
    ])
    assert store.candidates(["proj"], ["memory"], 10) == []
