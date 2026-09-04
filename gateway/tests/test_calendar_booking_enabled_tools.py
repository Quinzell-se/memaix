# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for tools.calendar.calendar_booking_enabled_get/set — memaix-src
card 9e035c73."""

from __future__ import annotations

import pytest

from memaix_gateway.acl import Acl, AccessDenied
from memaix_gateway.tools.calendar import (
    calendar_booking_enabled_get,
    calendar_booking_enabled_set,
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


def test_calendar_booking_enabled_get_denied_without_grant(acl):
    with pytest.raises(AccessDenied):
        calendar_booking_enabled_get(acl, "eve", "proj")


def test_calendar_booking_enabled_get_defaults_disabled(acl):
    assert calendar_booking_enabled_get(acl, "bob", "proj") == {"enabled": False}


def test_calendar_booking_enabled_set_denied_for_reader(acl):
    with pytest.raises(AccessDenied):
        calendar_booking_enabled_set(acl, "bob", "proj", True)


def test_calendar_booking_enabled_set_then_get_roundtrips(acl):
    result = calendar_booking_enabled_set(acl, "carol", "proj", True)
    assert result == {"ok": True, "enabled": True}
    assert calendar_booking_enabled_get(acl, "carol", "proj") == {"enabled": True}


def test_calendar_booking_enabled_set_can_turn_off(acl):
    calendar_booking_enabled_set(acl, "carol", "proj", True)
    result = calendar_booking_enabled_set(acl, "carol", "proj", False)
    assert result == {"ok": True, "enabled": False}
    assert calendar_booking_enabled_get(acl, "carol", "proj") == {"enabled": False}
