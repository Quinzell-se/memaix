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
                "files": {
                    "url": "https://nc.example.com/dav/files/acme/",
                    "user": "acme@example.com",
                    "password_ref": "env:NC_FILES_PW",
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


def test_catalog_registers_webdav_for_files(registry, acl, monkeypatch):
    monkeypatch.setenv("NC_FILES_PW", "f1les")
    seen = {}

    class _Sentinel:
        def __init__(self, url, user, password):
            seen["url"] = url
            seen["user"] = user
            seen["password"] = password

    import memaix_gateway.connectors.adapters.files_webdav as t_files

    monkeypatch.setattr(t_files, "WebDavFilesAdapter", _Sentinel)
    result = registry.get(acl, _FakeTokenStore(), "acme", "files", "alice")
    assert isinstance(result, _Sentinel)
    assert seen == {
        "url": "https://nc.example.com/dav/files/acme/",
        "user": "acme@example.com",
        "password": "f1les",
    }


def test_files_capability_does_not_read_vault_key(registry):
    """'files' must resolve against the new 'files' resource key, never 'vault'
    — the local vault has a completely different (bare string) shape."""
    acl = Acl(
        users={"alice": {"grants": {"acme": "owner"}}},
        projects={"acme": {"vault": "/srv/vaults/acme"}},  # no 'files' resource configured
    )
    with pytest.raises(ValueError, match="no files configured"):
        registry.get(acl, _FakeTokenStore(), "acme", "files", "alice")


def test_default_registry_is_a_lazy_singleton():
    from memaix_gateway.connectors.registry import default_registry

    first = default_registry()
    second = default_registry()
    assert first is second
