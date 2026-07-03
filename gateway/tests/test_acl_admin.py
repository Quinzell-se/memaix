# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the global admin flag (MEX-018) in acl.py.

Covers: admin gets implicit owner on every existing project, admin sees all
projects, non-admins are unaffected, and — the ordering fix — an unknown
project errors even for an admin instead of silently passing.
"""

from __future__ import annotations

import pytest

from memaix_gateway.acl import Acl, AccessDenied


def _acl() -> Acl:
    return Acl(
        users={
            "root": {"admin": True},
            "alice": {"grants": {"acme": "owner"}},
            "carol": {"grants": {"acme": "reader"}},
        },
        projects={"acme": {"vault": "/tmp/acme"}, "beta": {"vault": "/tmp/beta"}},
    )


def test_admin_has_implicit_owner_on_every_project():
    acl = _acl()
    # root has no grants at all, yet enforce passes at every level on any project.
    acl.enforce("root", "acme", "owner")
    acl.enforce("root", "beta", "owner")
    acl.enforce("root", "beta", "reader")


def test_admin_sees_all_projects():
    acl = _acl()
    assert acl.visible_projects("root") == ["acme", "beta"]


def test_non_admin_unaffected_by_admin_flag():
    acl = _acl()
    # carol is only a reader on acme; owner must still be denied.
    with pytest.raises(AccessDenied):
        acl.enforce("carol", "acme", "owner")
    # and she has no access to beta at all.
    with pytest.raises(AccessDenied):
        acl.enforce("carol", "beta", "reader")
    assert acl.visible_projects("carol") == ["acme"]


def test_is_admin_flag():
    acl = _acl()
    assert acl.is_admin("root") is True
    assert acl.is_admin("alice") is False
    assert acl.is_admin("nonexistent") is False


def test_disabled_user_denied_everything():
    """Kill-switch: a disabled user is denied every project, at every level."""
    acl = Acl(
        users={
            "alice": {"grants": {"acme": "owner"}, "disabled": True},
            "root": {"admin": True, "disabled": True},
        },
        projects={"acme": {"vault": "/tmp/acme"}},
    )
    assert acl.is_disabled("alice") is True
    with pytest.raises(AccessDenied, match="disabled"):
        acl.enforce("alice", "acme", "reader")
    # Even a disabled admin is locked out (lockout-prevention is a write-path
    # concern, not enforce's — enforce fails closed).
    with pytest.raises(AccessDenied, match="disabled"):
        acl.enforce("root", "acme", "owner")


def test_not_disabled_by_default():
    acl = _acl()
    assert acl.is_disabled("alice") is False
    # Sanity: a non-disabled user with a grant still passes.
    acl.enforce("alice", "acme", "owner")


def test_unknown_project_errors_even_for_admin():
    """Ordering fix: admin acting on a typo'd/nonexistent project gets a clear
    failure, not a silent pass that masks the mistake."""
    acl = _acl()
    with pytest.raises(AccessDenied, match="unknown project"):
        acl.enforce("root", "does-not-exist", "reader")
    # non-admin on unknown project also errors (regression guard).
    with pytest.raises(AccessDenied, match="unknown project"):
        acl.enforce("alice", "does-not-exist", "reader")
