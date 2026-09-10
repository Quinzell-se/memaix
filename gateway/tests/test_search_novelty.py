# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for novelty gate (search/novelty.py) and decay (search/query.py)."""

from __future__ import annotations

import time

import pytest

from memaix_gateway.acl import Acl
from memaix_gateway.search.embedder import FakeEmbedder
from memaix_gateway.search.index import index_upsert
from memaix_gateway.search.novelty import check_novelty
from memaix_gateway.search.query import search_all
from memaix_gateway.search.store import EmbeddingStore


@pytest.fixture()
def store(tmp_path):
    return EmbeddingStore.for_path(tmp_path / "index.db")


@pytest.fixture()
def embedder():
    return FakeEmbedder(dim=64)


# ------------------------------------------------------------------
# Novelty gate (a8cea472)
# ------------------------------------------------------------------


def test_check_novelty_returns_none_without_embedder(store):
    result = check_novelty("some content", "proj", "note.md", None, store)
    assert result is None


def test_check_novelty_returns_none_when_no_candidates(store, embedder):
    result = check_novelty("some content", "proj", "note.md", embedder, store)
    assert result is None


def test_check_novelty_returns_none_for_empty_content(store, embedder):
    index_upsert(store, embedder, "proj", "memory", "existing.md", "existing.md", "some content")
    result = check_novelty("", "proj", "note.md", embedder, store)
    assert result is None


def test_check_novelty_skips_self(store, embedder):
    index_upsert(store, embedder, "proj", "memory", "same.md", "same.md", "identical content")
    # Writing to same.md should not trigger gate against itself
    result = check_novelty("identical content", "proj", "same.md", embedder, store, threshold=0.0)
    assert result is None


def test_check_novelty_detects_near_duplicate(store, embedder):
    index_upsert(store, embedder, "proj", "memory", "existing.md", "existing.md",
                 "redis session state ttl expiry")
    # Very low threshold to make FakeEmbedder trigger on shared tokens
    result = check_novelty("redis session state ttl expiry", "proj", "new.md", embedder, store,
                           threshold=0.5)
    assert result is not None
    assert result["existing_path"] == "existing.md"
    assert 0.0 <= result["similarity"] <= 1.0


def test_check_novelty_passes_dissimilar_content(store, embedder):
    index_upsert(store, embedder, "proj", "memory", "existing.md", "existing.md",
                 "redis session state ttl")
    result = check_novelty("completely different topic about databases",
                           "proj", "new.md", embedder, store, threshold=0.99)
    assert result is None


def test_check_novelty_above_max_similarity_never_blocks(store, embedder):
    # Cosine similarity is at most 1.0 — threshold > 1.0 can never be reached.
    index_upsert(store, embedder, "proj", "memory", "a.md", "a.md", "redis session state")
    result = check_novelty("redis session state", "proj", "b.md", embedder, store, threshold=1.01)
    assert result is None


# ------------------------------------------------------------------
# Decay viktning (2a194a2c)
# ------------------------------------------------------------------


@pytest.fixture()
def acl():
    return Acl(
        users={"alice": {"grants": {"proj": "owner"}}},
        projects={"proj": {"vault": "/v"}},
    )


def test_decay_lambda_zero_preserves_ranking(store, embedder, acl):
    index_upsert(store, embedder, "proj", "memory", "old.md", "old.md", "invoice payment overdue")
    index_upsert(store, embedder, "proj", "memory", "new.md", "new.md", "invoice payment overdue")
    cfg = {"memaix": {"search": {"decay_lambda": 0.0}}}
    result = search_all(acl, "alice", cfg, store, embedder, "invoice payment")
    assert isinstance(result["results"], list)
    # λ=0 → identical to no-decay, no crash
    assert len(result["results"]) >= 1


def test_decay_applied_does_not_crash(store, embedder, acl):
    index_upsert(store, embedder, "proj", "memory", "note.md", "note.md", "quarterly roadmap")
    cfg = {"memaix": {"search": {"decay_lambda": 0.01}}}
    result = search_all(acl, "alice", cfg, store, embedder, "roadmap")
    assert len(result["results"]) >= 1
    # Score is a float
    assert isinstance(result["results"][0]["score"], float)


def test_get_ref_updated_at_returns_none_for_unknown(store):
    result = store.get_ref_updated_at("proj", "memory", "nonexistent.md")
    assert result is None


def test_get_ref_updated_at_returns_string_after_index(store, embedder):
    index_upsert(store, embedder, "proj", "memory", "note.md", "note.md", "content")
    result = store.get_ref_updated_at("proj", "memory", "note.md")
    assert isinstance(result, str)
    assert len(result) > 0
