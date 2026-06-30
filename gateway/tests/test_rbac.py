# SPDX-License-Identifier: AGPL-3.0-or-later
"""RBAC isolation tests — Fas 1 gate.

These tests are the mandatory first deliverable (AGENTS.md §2, BUILD.md Fas 1):
a user without a grant must be provably denied before any other code is built.

Fixtures:
  acl     — Acl with jimmy=owner/acme, carol=collaborator/acme.
  vault   — tmp_path vault dir with a single note.md file.
"""

from __future__ import annotations

import pytest

from memaix_gateway.acl import Acl, AccessDenied
from memaix_gateway.tools.files import list_files, read_file, search_files, write_file
from memaix_gateway.tools.whoami import whoami


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def vault(tmp_path):
    v = tmp_path / "vault"
    v.mkdir()
    (v / "note.md").write_text("hello memaix")
    (v / "sub").mkdir()
    (v / "sub" / "nested.md").write_text("deep content")
    return v


@pytest.fixture()
def acl(vault):
    return Acl(
        users={
            "alice": {"grants": {"acme": "owner", "project-a": "owner"}},
            "carol": {"grants": {"acme": "collaborator"}},
            "bob": {"grants": {"project-a": "owner"}},
        },
        projects={
            "acme": {"vault": str(vault)},
            "project-a": {"vault": str(vault)},
        },
    )


# ---------------------------------------------------------------------------
# Acl.enforce — core isolation proofs
# ---------------------------------------------------------------------------


def test_unknown_user_is_denied(acl):
    """A user not in ACL at all must be denied on any project."""
    with pytest.raises(AccessDenied):
        acl.enforce("ghost", "acme", "reader")


def test_user_denied_wrong_project(acl):
    """Carol has no grant on project-a and must be denied."""
    with pytest.raises(AccessDenied):
        acl.enforce("carol", "project-a", "reader")


def test_user_denied_insufficient_role(acl):
    """Carol is collaborator; requesting owner must fail."""
    with pytest.raises(AccessDenied):
        acl.enforce("carol", "acme", "owner")


def test_unknown_project_is_denied(acl):
    """Any access to a project not listed in ACL must be denied."""
    with pytest.raises(AccessDenied):
        acl.enforce("alice", "nonexistent", "reader")


def test_sufficient_role_passes(acl):
    """Correct roles must not raise."""
    acl.enforce("carol", "acme", "reader")
    acl.enforce("carol", "acme", "collaborator")
    acl.enforce("alice", "acme", "owner")


# ---------------------------------------------------------------------------
# files_* tool path — enforce() gates before filesystem
# ---------------------------------------------------------------------------


def test_files_list_denied_for_unknown_user(acl):
    with pytest.raises(AccessDenied):
        list_files(acl, "ghost", "acme")


def test_files_read_denied_for_unknown_user(acl):
    with pytest.raises(AccessDenied):
        read_file(acl, "ghost", "acme", "note.md")


def test_files_write_denied_for_unknown_user(acl):
    with pytest.raises(AccessDenied):
        write_file(acl, "ghost", "acme", "new.md", "data")


def test_files_search_denied_for_unknown_user(acl):
    with pytest.raises(AccessDenied):
        search_files(acl, "ghost", "acme", "hello")


def test_files_list_denied_wrong_project(acl):
    """Carol cannot list files in project-a."""
    with pytest.raises(AccessDenied):
        list_files(acl, "carol", "project-a")


# ---------------------------------------------------------------------------
# files_* happy path — granted users can access
# ---------------------------------------------------------------------------


def test_files_list_granted(acl):
    result = list_files(acl, "carol", "acme")
    names = {e["name"] for e in result}
    assert "note.md" in names


def test_files_read_granted(acl):
    content = read_file(acl, "alice", "acme", "note.md")
    assert content == "hello memaix"


def test_files_write_and_read_roundtrip(acl, vault):
    write_file(acl, "alice", "acme", "new.md", "written content")
    assert (vault / "new.md").read_text() == "written content"
    assert read_file(acl, "alice", "acme", "new.md") == "written content"


def test_files_search_finds_match(acl):
    results = search_files(acl, "carol", "acme", "hello")
    assert any("note.md" in r["path"] for r in results)


def test_files_search_finds_nested(acl):
    results = search_files(acl, "alice", "acme", "deep")
    assert any("nested.md" in r["path"] for r in results)


def test_files_list_subdir(acl):
    result = list_files(acl, "alice", "acme", "sub")
    assert any(e["name"] == "nested.md" for e in result)


# ---------------------------------------------------------------------------
# Path traversal guard
# ---------------------------------------------------------------------------


def test_path_traversal_blocked(acl):
    with pytest.raises((ValueError, FileNotFoundError)):
        read_file(acl, "alice", "acme", "../../etc/passwd")


def test_path_traversal_blocked_absolute(acl):
    with pytest.raises((ValueError, FileNotFoundError)):
        read_file(acl, "alice", "acme", "/etc/passwd")


# ---------------------------------------------------------------------------
# whoami
# ---------------------------------------------------------------------------


def test_whoami_returns_grants(acl):
    result = whoami(acl, "carol")
    assert result["user_id"] == "carol"
    assert result["projects"]["acme"]["role"] == "collaborator"
    assert "project-a" not in result["projects"]


def test_whoami_unknown_user_returns_empty_projects(acl):
    result = whoami(acl, "ghost")
    assert result["user_id"] == "ghost"
    assert result["projects"] == {}
