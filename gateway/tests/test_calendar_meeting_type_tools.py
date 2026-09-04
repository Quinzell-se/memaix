# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for tools.calendar.calendar_meeting_type_list/set/delete —
memaix-src card d0a1f633."""

from __future__ import annotations

import pytest

from memaix_gateway.acl import Acl, AccessDenied
from memaix_gateway.tools.calendar import (
    calendar_meeting_type_delete,
    calendar_meeting_type_list,
    calendar_meeting_type_set,
)


@pytest.fixture()
def acl(tmp_path):
    return Acl(
        users={
            "alice": {"grants": {"proj": "owner"}},
            "carol": {"grants": {"proj": "collaborator"}},
            "bob": {"grants": {"proj": "reader"}},
        },
        projects={
            "proj": {
                "vault": str(tmp_path),
                "calendar": {"url": "https://cal.example.com/dav/", "user": "alice", "password_ref": "env:X"},
            }
        },
    )


def _type(slug="quick", name="Quick sync", duration_min=30, **extra):
    return {"slug": slug, "name": name, "duration_min": duration_min, **extra}


def test_list_denied_without_grant(acl):
    with pytest.raises(AccessDenied):
        calendar_meeting_type_list(acl, "eve", "proj")


def test_list_defaults_empty(acl):
    assert calendar_meeting_type_list(acl, "bob", "proj") == []


def test_set_denied_for_reader(acl):
    with pytest.raises(AccessDenied):
        calendar_meeting_type_set(acl, "bob", "proj", [_type()])


def test_set_then_list_roundtrips(acl):
    result = calendar_meeting_type_set(acl, "carol", "proj", [_type()])
    assert result["ok"] is True
    assert calendar_meeting_type_list(acl, "carol", "proj") == result["types"]


def test_set_rejects_invalid_type_with_error_not_exception(acl):
    result = calendar_meeting_type_set(acl, "carol", "proj", [{"slug": "Bad Slug", "name": "x", "duration_min": 1}])
    assert result["ok"] is False
    assert "error" in result


def test_delete_denied_for_reader(acl):
    with pytest.raises(AccessDenied):
        calendar_meeting_type_delete(acl, "bob", "proj", "quick")


def test_delete_removes_type(acl):
    calendar_meeting_type_set(acl, "carol", "proj", [_type(slug="a", name="A"), _type(slug="b", name="B")])
    result = calendar_meeting_type_delete(acl, "carol", "proj", "a")
    assert result["ok"] is True
    assert [t["slug"] for t in result["types"]] == ["b"]
    assert [t["slug"] for t in calendar_meeting_type_list(acl, "carol", "proj")] == ["b"]
