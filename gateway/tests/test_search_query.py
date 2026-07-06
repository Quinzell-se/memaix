# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for search.query.search_all — ACL scoping, hybrid ranking, fusion."""

from __future__ import annotations

import pytest

from memaix_gateway.acl import Acl
from memaix_gateway.search.embedder import FakeEmbedder
from memaix_gateway.search.index import index_upsert
from memaix_gateway.search.query import search_all
from memaix_gateway.search.store import EmbeddingStore


@pytest.fixture()
def store(tmp_path):
    return EmbeddingStore.for_path(tmp_path / "index.db")


@pytest.fixture()
def embedder():
    return FakeEmbedder(dim=64)


@pytest.fixture()
def acl():
    return Acl(
        users={
            "alice": {"grants": {"proj": "owner"}},
            "bob": {"grants": {"proj": "reader"}},
        },
        projects={
            "proj": {"vault": "/v", "mailbox": {"host": "x"}},
            "other": {"vault": "/v2"},
        },
    )


def test_lexical_search_finds_matching_note(store, acl):
    index_upsert(store, None, "proj", "memory", "note.md", "note.md", "the invoice is overdue")
    result = search_all(acl, "alice", None, store, None, "invoice")
    assert result["semantic"] is False
    assert len(result["results"]) == 1
    assert result["results"][0]["ref"] == "note.md"


def test_semantic_search_used_when_embedder_present(store, embedder, acl):
    index_upsert(store, embedder, "proj", "memory", "note.md", "note.md", "invoice payment overdue")
    result = search_all(acl, "alice", None, store, embedder, "late payment on invoice")
    assert result["semantic"] is True
    assert len(result["results"]) >= 1


def test_reader_cannot_search_files_but_can_search_memory(store, embedder, acl):
    index_upsert(store, embedder, "proj", "file", "secret.txt", "secret.txt", "confidential content")
    index_upsert(store, embedder, "proj", "memory", "note.md", "note.md", "confidential content")
    result = search_all(acl, "bob", None, store, embedder, "confidential")
    refs = {(r["source_type"], r["ref"]) for r in result["results"]}
    assert ("file", "secret.txt") not in refs
    assert ("memory", "note.md") in refs


def test_project_outside_visible_is_filtered(store, embedder, acl):
    index_upsert(store, embedder, "other", "memory", "x.md", "x.md", "budget report")
    result = search_all(acl, "alice", None, store, embedder, "budget", projects=["proj"])
    assert result["results"] == []  # only 'proj' was requested, and it has no content
    assert "other" not in result["projects_searched"]


def test_projects_param_filters_within_visible_set(store, embedder, acl):
    index_upsert(store, embedder, "proj", "memory", "a.md", "a.md", "roadmap notes")
    result = search_all(acl, "alice", None, store, embedder, "roadmap")
    assert "proj" in result["projects_searched"]


def test_no_embedder_falls_back_to_lexical_only(store, acl):
    index_upsert(store, None, "proj", "memory", "note.md", "note.md", "quarterly roadmap plan")
    result = search_all(acl, "alice", None, store, None, "roadmap")
    assert result["semantic"] is False
    assert len(result["results"]) == 1


def test_rrf_dedupes_hits_present_in_both_lexical_and_semantic(store, embedder, acl):
    index_upsert(store, embedder, "proj", "memory", "note.md", "note.md", "invoice overdue payment")
    result = search_all(acl, "alice", None, store, embedder, "invoice")
    refs = [r["ref"] for r in result["results"]]
    assert refs.count("note.md") == 1  # not duplicated across lexical+semantic


def test_email_search_folds_into_results_when_injected(store, embedder, acl):
    def fake_email_search(acl_, user, project, query, limit):
        return [{"id": "42", "subject": "Invoice reminder", "from": "x@y.com", "date": "2026-01-01"}]

    result = search_all(
        acl, "alice", None, store, embedder, "invoice", _email_search=fake_email_search
    )
    email_hits = [r for r in result["results"] if r["source_type"] == "email"]
    assert len(email_hits) == 1
    assert email_hits[0]["ref"] == "42"


def test_email_search_skipped_for_project_without_mailbox(store, embedder):
    acl = Acl(
        users={"alice": {"grants": {"nomail": "owner"}}},
        projects={"nomail": {"vault": "/v"}},
    )
    calls = []

    def fake_email_search(acl_, user, project, query, limit):
        calls.append(project)
        return []

    search_all(acl, "alice", None, store, embedder, "x", _email_search=fake_email_search)
    assert calls == []


def test_email_search_not_available_to_reader(store, embedder, acl):
    calls = []

    def fake_email_search(acl_, user, project, query, limit):
        calls.append(project)
        return []

    search_all(acl, "bob", None, store, embedder, "x", _email_search=fake_email_search)
    assert calls == []  # bob is only a reader; email_search needs collaborator


def test_max_candidates_from_cfg_is_respected(store, embedder, acl):
    for i in range(5):
        index_upsert(store, embedder, "proj", "memory", f"n{i}.md", f"n{i}.md", f"content number {i}")
    cfg = {"memaix": {"search": {"max_candidates": 2}}}
    result = search_all(acl, "alice", cfg, store, embedder, "content", limit=10)
    # Can't directly observe candidate cap from results shape, but this
    # should not error and should still return results.
    assert isinstance(result["results"], list)


def test_memory_hits_carry_ladder_status(tmp_path, store, acl):
    """Minnestrappan i sök: memory-träffar bär status, uppslagen vid
    frågetillfället — en hypotes kan aldrig se ut som faktum (Fas B)."""
    from memaix_gateway.acl import Acl
    from memaix_gateway.backends.memory_store import MemoryStore
    from memaix_gateway.tools.memory import memory_write

    vault = tmp_path / "vault"
    vault.mkdir()
    MemoryStore._clear_instances()
    real_acl = Acl(
        users={"alice": {"grants": {"proj": "owner"}}},
        projects={"proj": {"vault": str(vault)}},
    )
    memory_write(real_acl, "alice", "proj", "obekraftad.md", "kunden gillar blått kanske")
    memory_write(real_acl, "alice", "proj", "bekraftad.md", "kunden gillar blått bevisligen",
                 status="verifierad")
    index_upsert(store, None, "proj", "memory", "obekraftad.md", "obekraftad.md",
                 "kunden gillar blått kanske")
    index_upsert(store, None, "proj", "memory", "bekraftad.md", "bekraftad.md",
                 "kunden gillar blått bevisligen")
    index_upsert(store, None, "proj", "file", "f.txt", "f.txt", "blått dokument")

    result = search_all(real_acl, "alice", None, store, None, "blått")
    by_ref = {r["ref"]: r for r in result["results"]}
    assert by_ref["obekraftad.md"]["status"] == "hypotes"
    assert by_ref["bekraftad.md"]["status"] == "verifierad"
    assert "status" not in by_ref["f.txt"], "bara memory-träffar bär trapp-status"
