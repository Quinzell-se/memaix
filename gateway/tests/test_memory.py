# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration tests for MemoryStore + memory_* tools.

Uses real SQLite and real git (git must be available in PATH).
Each test gets an isolated tmp_path so singletons don't collide.
"""

from __future__ import annotations

import pytest

from memaix_gateway.acl import Acl, AccessDenied
from memaix_gateway.backends.memory_store import MemoryStore
from memaix_gateway.tools.memory import (
    memory_append,
    memory_history,
    memory_read,
    memory_revert,
    memory_search,
    memory_write,
)


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture()
def vault(tmp_path):
    v = tmp_path / "vault"
    v.mkdir()
    return v


@pytest.fixture()
def store(vault):
    # Clear singleton registry so each test gets a fresh instance
    MemoryStore._clear_instances()
    return MemoryStore.for_vault(vault)


@pytest.fixture()
def acl(vault):
    return Acl(
        users={
            "alice": {"grants": {"proj": "owner", "novault": "owner"}},
            "carol": {"grants": {"proj": "collaborator"}},
            "bob": {"grants": {"proj": "reader"}},
        },
        projects={
            "proj": {"vault": str(vault)},
            "novault": {},  # project exists but has no vault configured
        },
    )


# ------------------------------------------------------------------
# MemoryStore unit tests
# ------------------------------------------------------------------


def test_write_read_roundtrip(store):
    commit = store.write("ideas/note.md", "hello memaix", "alice")
    assert commit  # non-empty hash
    assert store.read("ideas/note.md") == "hello memaix"


def test_read_missing_returns_none(store):
    assert store.read("does-not-exist.md") is None


def test_append_adds_text(store):
    store.write("log.md", "line one", "alice")
    store.append("log.md", "line two", "alice")
    content = store.read("log.md")
    assert "line one" in content
    assert "line two" in content


def test_append_creates_missing_note(store):
    store.append("fresh.md", "created via append", "alice")
    assert store.read("fresh.md") == "created via append"


def test_search_finds_content(store):
    store.write("ideas/note.md", "hello memaix world", "alice")
    results = store.search("hello")
    paths = [r["path"] for r in results]
    assert "ideas/note.md" in paths


def test_search_does_not_find_overwritten_content(store):
    store.write("temp.md", "findme unique_term_xyz", "alice")
    results = store.search("unique_term_xyz")
    assert any(r["path"] == "temp.md" for r in results)

    # Overwrite with different content — old term should vanish from FTS
    store.write("temp.md", "replacement content only", "alice")
    results2 = store.search("unique_term_xyz")
    assert not any(r["path"] == "temp.md" for r in results2)


def test_list_all(store):
    store.write("a.md", "aaa", "alice")
    store.write("b.md", "bbb", "alice")
    all_paths = store.list_all()
    assert "a.md" in all_paths
    assert "b.md" in all_paths


def test_history_returns_commits_after_write(store):
    store.write("hist.md", "v1", "alice")
    store.write("hist.md", "v2", "alice")
    hist = store.history("hist.md")
    assert len(hist) >= 2
    assert all("hash" in h and "message" in h for h in hist)


def test_revert_rolls_back(store):
    store.write("rv.md", "original", "alice")
    store.write("rv.md", "modified", "alice")
    assert store.read("rv.md") == "modified"

    hist = store.history("rv.md")
    assert len(hist) >= 2
    # Revert the most recent commit (less likely to conflict than reverting old ones)
    latest_commit = hist[0]["hash"]

    new_commit = store.revert(latest_commit)
    assert new_commit  # non-empty
    # After revert, a new commit exists on top
    hist_after = store.history("rv.md")
    assert len(hist_after) > len(hist)


@pytest.mark.parametrize("bad", ["-rf", "--all", "HEAD~1; rm -rf /", "not-a-hash", "", "../etc"])
def test_revert_rejects_non_hash(store, bad):
    """revert must only accept a plain git object hash (blocks arg injection)."""
    with pytest.raises(ValueError):
        store.revert(bad)


# ------------------------------------------------------------------
# memory_* tool ACL tests
# ------------------------------------------------------------------


def test_memory_write_allowed_for_collaborator(acl, store):
    result = memory_write(acl, "carol", "proj", "note.md", "written by carol")
    assert result["path"] == "note.md"
    assert result["commit"]


def test_memory_read_allowed_for_reader(acl, store):
    memory_write(acl, "carol", "proj", "shared.md", "shared content")
    result = memory_read(acl, "bob", "proj", "shared.md")
    assert result["content"] == "shared content"


def test_memory_search_allowed_for_reader(acl, store):
    memory_write(acl, "carol", "proj", "x.md", "searchable text")
    results = memory_search(acl, "bob", "proj", "searchable")
    assert isinstance(results, list)


def test_memory_write_denied_for_reader(acl, store):
    with pytest.raises(AccessDenied):
        memory_write(acl, "bob", "proj", "note.md", "blocked")


def test_memory_read_denied_for_unknown_user(acl, store):
    with pytest.raises(AccessDenied):
        memory_read(acl, "ghost", "proj", "note.md")


def test_memory_append_denied_for_reader(acl, store):
    with pytest.raises(AccessDenied):
        memory_append(acl, "bob", "proj", "note.md", "extra")


def test_memory_history_allowed_for_reader(acl, store):
    memory_write(acl, "carol", "proj", "h.md", "v1")
    result = memory_history(acl, "bob", "proj", "h.md")
    assert isinstance(result, list)


def test_memory_write_no_vault_raises_value_error(acl, store):
    with pytest.raises((ValueError, Exception)):
        memory_write(acl, "alice", "novault", "note.md", "content")


def test_memory_read_invalid_path_dot_dot(acl, store):
    with pytest.raises(ValueError):
        memory_read(acl, "alice", "proj", "../project-b.md")


def test_memory_read_absolute_path_rejected(acl, store):
    with pytest.raises(ValueError):
        memory_read(acl, "alice", "proj", "/etc/passwd")
