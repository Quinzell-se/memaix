# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for connectors.booking_settings — memaix-src card 9e035c73."""

from __future__ import annotations

import pytest

from memaix_gateway.connectors.booking_settings import BookingSettingsStore


@pytest.fixture()
def acl_with_vault(tmp_path):
    from memaix_gateway.acl import Acl

    return Acl(
        users={"alice": {"grants": {"proj": "owner"}}},
        projects={"proj": {"vault": str(tmp_path), "calendar": {"type": "caldav"}}},
    )


def test_store_get_defaults_to_disabled_when_never_set(acl_with_vault):
    store = BookingSettingsStore(acl_with_vault, "proj", "alice")
    assert store.get() == {"enabled": False}


def test_store_set_true_then_get_roundtrips(acl_with_vault):
    store = BookingSettingsStore(acl_with_vault, "proj", "alice")
    store.set(True)
    assert store.get() == {"enabled": True}


def test_store_set_false_then_get_roundtrips(acl_with_vault):
    store = BookingSettingsStore(acl_with_vault, "proj", "alice")
    store.set(True)
    store.set(False)
    assert store.get() == {"enabled": False}


def test_store_set_coerces_truthy_values_to_bool(acl_with_vault):
    store = BookingSettingsStore(acl_with_vault, "proj", "alice")
    store.set(1)
    assert store.get() == {"enabled": True}


def test_store_is_scoped_per_user(acl_with_vault):
    alice = BookingSettingsStore(acl_with_vault, "proj", "alice")
    bob = BookingSettingsStore(acl_with_vault, "proj", "bob")
    alice.set(True)
    assert bob.get() == {"enabled": False}
