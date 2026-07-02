# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for connectors.catalog — proves the registry builds today's real
mail/calendar adapters from project config (FEATURE-CONNECTOR-FRAMEWORK.md §6)."""

from __future__ import annotations

import pytest

from memaix_gateway.acl import Acl
from memaix_gateway.connectors.catalog import register_defaults
from memaix_gateway.connectors.registry import ConnectorRegistry


class _FakeTokenStore:
    def list_accounts(self, user):
        return []

    def load_one(self, user, provider, account):
        return None


@pytest.fixture()
def acl():
    return Acl(
        users={"alice": {"grants": {"acme": "owner"}}},
        projects={
            "acme": {
                "vault": "/srv/vaults/acme",
                "mailbox": {"host": "imap.example.com", "user": "acme@example.com", "password_ref": "env:PW"},
                "calendar": {"url": "https://caldav.example.com/acme/", "user": "acme@example.com"},
                "contacts": {
                    "url": "https://nc.example.com/dav/contacts/",
                    "user": "acme@example.com",
                    "password_ref": "env:NC_PW",
                },
            }
        },
    )


@pytest.fixture()
def registry():
    r = ConnectorRegistry()
    register_defaults(r)
    return r


def test_catalog_registers_imap_for_mail(registry, acl, monkeypatch):
    sentinel = object()
    import memaix_gateway.tools.email as t_email

    monkeypatch.setattr(t_email, "_make_mailbox", lambda acl, project: sentinel)
    result = registry.get(acl, _FakeTokenStore(), "acme", "mail", "alice")
    assert result is sentinel


def test_catalog_registers_caldav_for_calendar(registry, acl, monkeypatch):
    sentinel = object()
    import memaix_gateway.tools.calendar as t_cal

    monkeypatch.setattr(t_cal, "_RealDavAdapter", lambda acl, project: sentinel)
    result = registry.get(acl, _FakeTokenStore(), "acme", "calendar", "alice")
    assert result is sentinel


def test_catalog_registers_carddav_for_contacts(registry, acl, monkeypatch):
    monkeypatch.setenv("NC_PW", "s3cret")
    seen = {}

    class _Sentinel:
        def __init__(self, url, user, password):
            seen["url"] = url
            seen["user"] = user
            seen["password"] = password

    import memaix_gateway.connectors.adapters.contacts_carddav as t_contacts

    monkeypatch.setattr(t_contacts, "CardDavContactsAdapter", _Sentinel)
    result = registry.get(acl, _FakeTokenStore(), "acme", "contacts", "alice")
    assert isinstance(result, _Sentinel)
    assert seen == {
        "url": "https://nc.example.com/dav/contacts/",
        "user": "acme@example.com",
        "password": "s3cret",
    }


def test_default_registry_is_a_lazy_singleton():
    from memaix_gateway.connectors.registry import default_registry

    first = default_registry()
    second = default_registry()
    assert first is second
