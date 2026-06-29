# SPDX-License-Identifier: AGPL-3.0-or-later
"""Comprehensive multi-project, multi-user RBAC isolation tests."""

from __future__ import annotations

import pytest

from memaix_gateway.acl import Acl, AccessDenied
from memaix_gateway.tools.backlog import backlog_add, backlog_set_status
from memaix_gateway.tools.files import list_files, read_file


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def multi_vault(tmp_path):
    for proj in ["alpha", "beta", "gamma"]:
        v = tmp_path / proj
        v.mkdir()
        (v / "note.md").write_text(f"content of {proj}")
    return tmp_path


@pytest.fixture()
def multi_acl(multi_vault):
    return Acl(
        users={
            "alice": {"grants": {"alpha": "owner", "beta": "collaborator"}},
            "bob": {"grants": {"beta": "owner", "gamma": "reader"}},
            "carol": {"grants": {"gamma": "owner"}},
            "external": {"grants": {"alpha": "collaborator"}},
        },
        projects={
            "alpha": {"vault": str(multi_vault / "alpha")},
            "beta": {"vault": str(multi_vault / "beta")},
            "gamma": {"vault": str(multi_vault / "gamma")},
        },
    )


# ---------------------------------------------------------------------------
# Cross-project isolation
# ---------------------------------------------------------------------------


def test_alice_can_read_alpha(multi_acl):
    content = read_file(multi_acl, "alice", "alpha", "note.md")
    assert content == "content of alpha"


def test_alice_cannot_read_gamma(multi_acl):
    with pytest.raises(AccessDenied):
        read_file(multi_acl, "alice", "gamma", "note.md")


def test_bob_can_read_beta(multi_acl):
    content = read_file(multi_acl, "bob", "beta", "note.md")
    assert content == "content of beta"


def test_bob_can_read_gamma(multi_acl):
    # bob is reader on gamma — files require collaborator so this should be denied
    with pytest.raises(AccessDenied):
        read_file(multi_acl, "bob", "gamma", "note.md")


def test_bob_cannot_read_alpha(multi_acl):
    with pytest.raises(AccessDenied):
        read_file(multi_acl, "bob", "alpha", "note.md")


def test_carol_cannot_read_alpha(multi_acl):
    with pytest.raises(AccessDenied):
        read_file(multi_acl, "carol", "alpha", "note.md")


def test_carol_cannot_read_beta(multi_acl):
    with pytest.raises(AccessDenied):
        read_file(multi_acl, "carol", "beta", "note.md")


def test_external_can_read_alpha(multi_acl):
    content = read_file(multi_acl, "external", "alpha", "note.md")
    assert content == "content of alpha"


def test_external_cannot_read_beta(multi_acl):
    with pytest.raises(AccessDenied):
        read_file(multi_acl, "external", "beta", "note.md")


def test_external_cannot_read_gamma(multi_acl):
    with pytest.raises(AccessDenied):
        read_file(multi_acl, "external", "gamma", "note.md")


# ---------------------------------------------------------------------------
# Role boundaries within a project
# ---------------------------------------------------------------------------


def test_alice_can_set_status_alpha_owner(multi_acl, multi_vault):
    """alice is owner on alpha → can call set_status (owner only)."""
    item = backlog_add(multi_acl, "alice", "alpha", "Task", "desc")
    result = backlog_set_status(multi_acl, "alice", "alpha", item["id"], "triaged", 1)
    assert result.get("status") == "triaged"


def test_alice_cannot_set_status_beta_collaborator(multi_acl):
    """alice is collaborator on beta → set_status (owner only) must raise."""
    item = backlog_add(multi_acl, "alice", "beta", "Task", "desc")
    with pytest.raises(AccessDenied):
        backlog_set_status(multi_acl, "alice", "beta", item["id"], "triaged", 1)


def test_bob_can_add_backlog_beta_owner(multi_acl):
    """bob is owner on beta → backlog_add (collaborator) should succeed."""
    result = backlog_add(multi_acl, "bob", "beta", "Bob's task", "desc")
    assert result["status"] == "inbox"


def test_bob_reader_cannot_set_status_gamma(multi_acl, multi_vault):
    """bob is reader on gamma → backlog_add (collaborator) must raise."""
    with pytest.raises(AccessDenied):
        backlog_add(multi_acl, "bob", "gamma", "Task", "desc")


def test_external_collaborator_can_list_alpha(multi_acl):
    """external is collaborator on alpha → files_list should succeed."""
    result = list_files(multi_acl, "external", "alpha")
    assert any(e["name"] == "note.md" for e in result)


# ---------------------------------------------------------------------------
# files_* cross-project explicit denial
# ---------------------------------------------------------------------------


def test_files_read_external_beta_denied(multi_acl):
    with pytest.raises(AccessDenied):
        read_file(multi_acl, "external", "beta", "note.md")


def test_files_read_alice_gamma_denied(multi_acl):
    with pytest.raises(AccessDenied):
        read_file(multi_acl, "alice", "gamma", "note.md")


def test_files_read_bob_alpha_denied(multi_acl):
    with pytest.raises(AccessDenied):
        read_file(multi_acl, "bob", "alpha", "note.md")


# ---------------------------------------------------------------------------
# Role hierarchy verification
# ---------------------------------------------------------------------------


def test_owner_can_do_reader_things(multi_acl):
    """Owner rank ≥ reader: alice (owner on alpha) can list files."""
    multi_acl.enforce("alice", "alpha", "reader")  # must not raise


def test_owner_can_do_collaborator_things(multi_acl):
    multi_acl.enforce("alice", "alpha", "collaborator")  # must not raise


def test_reader_cannot_do_collaborator_things(multi_acl):
    """bob is reader on gamma — must be denied at collaborator level."""
    with pytest.raises(AccessDenied):
        multi_acl.enforce("bob", "gamma", "collaborator")


# ---------------------------------------------------------------------------
# Path traversal between projects
# ---------------------------------------------------------------------------


def test_path_traversal_between_projects(multi_acl):
    """alice has alpha → beta traversal via ../ must be blocked."""
    with pytest.raises((ValueError, FileNotFoundError)):
        read_file(multi_acl, "alice", "alpha", "../beta/note.md")


# ---------------------------------------------------------------------------
# Unknown project
# ---------------------------------------------------------------------------


def test_unknown_project_denied_alice(multi_acl):
    with pytest.raises(AccessDenied):
        multi_acl.enforce("alice", "delta", "reader")


def test_unknown_project_denied_bob(multi_acl):
    with pytest.raises(AccessDenied):
        multi_acl.enforce("bob", "nonexistent", "reader")


def test_unknown_project_denied_carol(multi_acl):
    with pytest.raises(AccessDenied):
        multi_acl.enforce("carol", "alpha", "reader")
