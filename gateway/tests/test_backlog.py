# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration tests for backlog_* tools.

Uses real filesystem (tmp_path).  No network, no git required.
"""

from __future__ import annotations

import pytest

from memaix_gateway.acl import Acl, AccessDenied
from memaix_gateway.tools.backlog import (
    backlog_add,
    backlog_assign,
    backlog_comment,
    backlog_get,
    backlog_list,
    backlog_score,
    backlog_set_status,
)


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture()
def vault(tmp_path):
    v = tmp_path / "vault"
    v.mkdir()
    (v / "backlog").mkdir()
    return v


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
            "novault": {},
        },
    )


# ------------------------------------------------------------------
# Happy-path CRUD
# ------------------------------------------------------------------


def test_add_list_get_roundtrip(acl):
    r = backlog_add(acl, "carol", "proj", "My feature", "Detailed description", category="ux")
    assert r["status"] == "inbox"
    item_id = r["id"]
    assert len(item_id) == 8  # 8 hex chars

    items = backlog_list(acl, "bob", "proj")
    assert any(i["id"] == item_id for i in items)

    item = backlog_get(acl, "bob", "proj", item_id)
    assert item["title"] == "My feature"
    assert item["description"] == "Detailed description"
    assert item["category"] == "ux"
    assert item["version"] == 1


def test_list_filter_by_status(acl):
    r1 = backlog_add(acl, "carol", "proj", "Item A", "desc A")
    r2 = backlog_add(acl, "carol", "proj", "Item B", "desc B")
    # Promote r2 to triaged
    backlog_set_status(acl, "alice", "proj", r2["id"], "triaged", expected_version=1)

    inbox_items = backlog_list(acl, "bob", "proj", status="inbox")
    assert any(i["id"] == r1["id"] for i in inbox_items)
    assert not any(i["id"] == r2["id"] for i in inbox_items)

    triaged_items = backlog_list(acl, "bob", "proj", status="triaged")
    assert any(i["id"] == r2["id"] for i in triaged_items)


def test_score_updates_fields(acl):
    r = backlog_add(acl, "carol", "proj", "Scoreable", "desc")
    item_id = r["id"]

    result = backlog_score(acl, "carol", "proj", item_id, expected_version=1, value=4, complexity=3)
    assert result.get("conflict") is None
    assert result["version"] == 2

    item = backlog_get(acl, "bob", "proj", item_id)
    assert item["value"] == 4
    assert item["complexity"] == 3


def test_comment_appends_to_description(acl):
    r = backlog_add(acl, "carol", "proj", "Commentable", "original desc")
    item_id = r["id"]

    result = backlog_comment(acl, "carol", "proj", item_id, "great idea!", expected_version=1)
    assert result["ok"] is True

    item = backlog_get(acl, "bob", "proj", item_id)
    assert "great idea!" in item["description"]
    assert item["version"] == 2


def test_set_status_transitions(acl):
    r = backlog_add(acl, "carol", "proj", "Stateful", "desc")
    item_id = r["id"]

    result = backlog_set_status(acl, "alice", "proj", item_id, "approved", expected_version=1)
    assert result["status"] == "approved"
    assert result["commit"] == "local"

    item = backlog_get(acl, "bob", "proj", item_id)
    assert item["status"] == "approved"
    assert item["version"] == 2


# ------------------------------------------------------------------
# Optimistic locking
# ------------------------------------------------------------------


def test_optimistic_lock_conflict_on_stale_version(acl):
    r = backlog_add(acl, "carol", "proj", "Lock test", "desc")
    item_id = r["id"]

    # First update succeeds
    backlog_score(acl, "carol", "proj", item_id, expected_version=1, value=5)

    # Second update with stale version → conflict
    result = backlog_score(acl, "carol", "proj", item_id, expected_version=1, risk=2)
    assert result["conflict"] is True
    assert result["current_version"] == 2


def test_optimistic_lock_comment_conflict(acl):
    r = backlog_add(acl, "carol", "proj", "Comment lock", "desc")
    item_id = r["id"]

    backlog_comment(acl, "carol", "proj", item_id, "first comment", expected_version=1)
    result = backlog_comment(acl, "carol", "proj", item_id, "stale comment", expected_version=1)
    assert result["conflict"] is True
    assert result["current_version"] == 2


def test_optimistic_lock_set_status_conflict(acl):
    r = backlog_add(acl, "carol", "proj", "Status lock", "desc")
    item_id = r["id"]

    backlog_set_status(acl, "alice", "proj", item_id, "triaged", expected_version=1)
    result = backlog_set_status(acl, "alice", "proj", item_id, "evaluated", expected_version=1)
    assert result["conflict"] is True


# ------------------------------------------------------------------
# ACL enforcement
# ------------------------------------------------------------------


def test_add_denied_for_reader(acl):
    with pytest.raises(AccessDenied):
        backlog_add(acl, "bob", "proj", "title", "desc")


def test_set_status_denied_for_collaborator(acl):
    r = backlog_add(acl, "carol", "proj", "title", "desc")
    with pytest.raises(AccessDenied):
        backlog_set_status(acl, "carol", "proj", r["id"], "approved", expected_version=1)


def test_set_status_denied_for_unknown_user(acl):
    r = backlog_add(acl, "carol", "proj", "title", "desc")
    with pytest.raises(AccessDenied):
        backlog_set_status(acl, "ghost", "proj", r["id"], "approved", expected_version=1)


def test_list_denied_for_unknown_user(acl):
    with pytest.raises(AccessDenied):
        backlog_list(acl, "ghost", "proj")


# ------------------------------------------------------------------
# Validation
# ------------------------------------------------------------------


def test_invalid_status_raises_value_error(acl):
    r = backlog_add(acl, "carol", "proj", "title", "desc")
    with pytest.raises(ValueError):
        backlog_set_status(acl, "alice", "proj", r["id"], "INVALID", expected_version=1)


def test_score_out_of_range_raises_value_error(acl):
    r = backlog_add(acl, "carol", "proj", "title", "desc")
    with pytest.raises(ValueError):
        backlog_score(acl, "carol", "proj", r["id"], expected_version=1, value=8)


def test_score_zero_raises_value_error(acl):
    r = backlog_add(acl, "carol", "proj", "title", "desc")
    with pytest.raises(ValueError):
        backlog_score(acl, "carol", "proj", r["id"], expected_version=1, complexity=0)


def test_corrupted_frontmatter_status_is_skipped_by_list(acl, vault):
    r = backlog_add(acl, "carol", "proj", "title", "desc")
    path = vault / "backlog" / f"{r['id']}.md"
    path.write_text(path.read_text().replace("status: inbox", "status: not-a-real-status"))
    assert backlog_list(acl, "bob", "proj") == []
    with pytest.raises(ValueError):
        backlog_get(acl, "bob", "proj", r["id"])


def test_get_missing_item_raises_file_not_found(acl):
    with pytest.raises(FileNotFoundError):
        backlog_get(acl, "bob", "proj", "deadbeef")


def test_no_vault_raises_value_error(acl):
    with pytest.raises(ValueError):
        backlog_add(acl, "alice", "novault", "title", "desc")


# ------------------------------------------------------------------
# Path traversal — a malicious id must never escape the backlog dir
# ------------------------------------------------------------------


@pytest.mark.parametrize("evil_id", ["../../secret", "../escape", "a/b", "..", "with space", ""])
def test_backlog_get_rejects_traversal(acl, evil_id):
    with pytest.raises(ValueError):
        backlog_get(acl, "bob", "proj", evil_id)


@pytest.mark.parametrize("evil_id", ["../../secret", "a/b"])
def test_backlog_score_rejects_traversal(acl, evil_id):
    with pytest.raises(ValueError):
        backlog_score(acl, "carol", "proj", evil_id, expected_version=1, value=3)


@pytest.mark.parametrize("evil_id", ["../../secret", "a/b"])
def test_backlog_set_status_rejects_traversal(acl, evil_id):
    with pytest.raises(ValueError):
        backlog_set_status(acl, "alice", "proj", evil_id, "done", expected_version=1)


def test_backlog_write_outside_vault_is_blocked(acl, vault, tmp_path):
    """A traversal id must not read or overwrite a file above the vault."""
    outside = tmp_path / "secret.md"
    outside.write_text("---\nid: x\nversion: 1\n---\nTOP SECRET\n")
    with pytest.raises(ValueError):
        backlog_get(acl, "alice", "proj", "../../secret")
    # The outside file is untouched.
    assert "TOP SECRET" in outside.read_text()


# ------------------------------------------------------------------
# Assignment — FEATURE-AGENT-TEAM fas 1
# ------------------------------------------------------------------


def test_assign_to_known_user(acl):
    r = backlog_add(acl, "carol", "proj", "Build API", "desc")
    result = backlog_assign(acl, "alice", "proj", r["id"], "carol", expected_version=1)
    assert result["assignee"] == "carol" and result["version"] == 2
    item = backlog_get(acl, "bob", "proj", r["id"])
    assert item["assignee"] == "carol"


def test_assign_surfaces_on_board_card(acl, vault):
    from memaix_gateway.board import store

    r = backlog_add(acl, "carol", "proj", "Wire auth", "desc")
    backlog_assign(acl, "alice", "proj", r["id"], "carol", expected_version=1)
    card = next(c for c in store.list_backlog(vault) if c["id"] == r["id"])
    assert card["assignee"] == "carol", "boarden visar vem som äger raden"


def test_unassign_with_empty(acl):
    r = backlog_add(acl, "carol", "proj", "t", "d")
    backlog_assign(acl, "alice", "proj", r["id"], "carol", expected_version=1)
    result = backlog_assign(acl, "alice", "proj", r["id"], "", expected_version=2)
    assert result["assignee"] is None


def test_assign_unknown_user_rejected(acl):
    r = backlog_add(acl, "carol", "proj", "t", "d")
    with pytest.raises(ValueError, match="unknown assignee"):
        backlog_assign(acl, "alice", "proj", r["id"], "spöke", expected_version=1)


def test_assign_denied_for_non_owner(acl):
    r = backlog_add(acl, "carol", "proj", "t", "d")
    with pytest.raises(AccessDenied):
        backlog_assign(acl, "carol", "proj", r["id"], "carol", expected_version=1)  # collaborator


def test_assign_optimistic_lock_conflict(acl):
    r = backlog_add(acl, "carol", "proj", "t", "d")
    backlog_assign(acl, "alice", "proj", r["id"], "carol", expected_version=1)
    stale = backlog_assign(acl, "alice", "proj", r["id"], "bob", expected_version=1)
    assert stale == {"conflict": True, "current_version": 2}
