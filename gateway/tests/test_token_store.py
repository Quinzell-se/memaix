# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the encrypted per-user OAuth token store."""

from __future__ import annotations

import sqlite3

import pytest
from cryptography.fernet import Fernet

from memaix_gateway.backends.token_store import TokenStore


@pytest.fixture()
def store(tmp_path):
    key = Fernet.generate_key()
    return TokenStore.for_path(tmp_path / "tokens.db", key)


def test_store_and_load(store):
    """Store then load_one roundtrip returns original data."""
    data = {"access_token": "abc123", "refresh_token": "xyz"}
    store.store("alice", "google", "alice@example.com", data)
    loaded = store.load_one("alice", "google", "alice@example.com")
    assert loaded == data


def test_encrypted_at_rest(tmp_path):
    """Raw BLOB in SQLite must not contain the plaintext token value."""
    key = Fernet.generate_key()
    path = tmp_path / "enc.db"
    s = TokenStore.for_path(path, key)
    secret_value = "super-secret-token-99999"
    s.store("user1", "google", "user1@example.com", {"access_token": secret_value})

    conn = sqlite3.connect(str(path))
    row = conn.execute("SELECT encrypted_data FROM user_tokens").fetchone()
    conn.close()

    raw_blob = bytes(row[0])
    assert secret_value.encode() not in raw_blob


def test_overwrite_updates(store):
    """Storing the same key twice updates, not duplicates."""
    store.store("bob", "google", "bob@example.com", {"v": 1})
    store.store("bob", "google", "bob@example.com", {"v": 2})
    loaded = store.load_one("bob", "google", "bob@example.com")
    assert loaded == {"v": 2}

    accounts = store.list_accounts("bob")
    assert len(accounts) == 1


def test_list_accounts(store):
    """Multiple stored tokens appear in list_accounts."""
    store.store("carol", "google", "carol@gmail.com", {"scope": "email profile"})
    store.store("carol", "microsoft", "carol@outlook.com", {"scope": "mail"})
    accounts = store.list_accounts("carol")
    assert len(accounts) == 2
    providers = {a["provider"] for a in accounts}
    assert providers == {"google", "microsoft"}


def test_delete_returns_true(store):
    """Deleting an existing record returns True."""
    store.store("dave", "google", "dave@example.com", {"x": 1})
    result = store.delete("dave", "google", "dave@example.com")
    assert result is True
    assert store.load_one("dave", "google", "dave@example.com") is None


def test_delete_missing_returns_false(store):
    """Deleting a non-existent record returns False."""
    result = store.delete("nobody", "google", "nobody@example.com")
    assert result is False


def test_mark_needs_relink(store):
    """mark_needs_relink sets status='needs_relink'."""
    store.store("eve", "microsoft", "eve@example.com", {"scope": "mail"})
    store.mark_needs_relink("eve", "microsoft", "eve@example.com")
    accounts = store.list_accounts("eve")
    assert len(accounts) == 1
    assert accounts[0]["status"] == "needs_relink"


def test_different_users_isolated(store):
    """User A's tokens are not visible to user B."""
    store.store("alice", "google", "alice@example.com", {"token": "alice-secret"})
    store.store("bob", "google", "bob@example.com", {"token": "bob-secret"})

    alice_accounts = store.list_accounts("alice")
    bob_accounts = store.list_accounts("bob")

    assert len(alice_accounts) == 1
    assert alice_accounts[0]["account"] == "alice@example.com"
    assert len(bob_accounts) == 1
    assert bob_accounts[0]["account"] == "bob@example.com"

    # Cross-load returns None
    assert store.load_one("alice", "google", "bob@example.com") is None
    assert store.load_one("bob", "google", "alice@example.com") is None
