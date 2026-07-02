# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the board's session-auth hardening: fail-closed on the default
signing secret in HTTP mode, and per-user password binding so a shared
password can't authenticate as a different user."""

from __future__ import annotations

import hashlib
import importlib

import pytest

import memaix_gateway.board.routes as routes


def _hash(password: str, salt: bytes = b"\x01" * 16) -> str:
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return f"{salt.hex()}:{derived.hex()}"


@pytest.fixture()
def reload_routes(monkeypatch):
    """routes.py reads _ALLOWED_USERS / _PASSWORD_HASH at import time, so tests
    that change them must reimport the module after setting env."""
    def _reload(**env):
        for k, v in env.items():
            if v is None:
                monkeypatch.delenv(k, raising=False)
            else:
                monkeypatch.setenv(k, v)
        return importlib.reload(routes)
    yield _reload
    importlib.reload(routes)  # restore defaults for other tests


# ------------------------------------------------------------------
# Fail-closed on default secret in HTTP mode
# ------------------------------------------------------------------


def test_default_secret_disables_board_in_http_mode(reload_routes):
    r = reload_routes(MEMAIX_TRANSPORT="http", HYDRA_SYSTEM_SECRET=None, MEMAIX_ALLOW_DEV_SECRET=None)
    with pytest.raises(r.BoardDisabled):
        r._secret()


def test_default_secret_allowed_in_stdio_mode(reload_routes):
    r = reload_routes(MEMAIX_TRANSPORT=None, HYDRA_SYSTEM_SECRET=None)
    assert r._secret()  # stdio/dev — default secret is acceptable


def test_default_secret_allowed_with_explicit_optin(reload_routes):
    r = reload_routes(MEMAIX_TRANSPORT="http", HYDRA_SYSTEM_SECRET=None, MEMAIX_ALLOW_DEV_SECRET="1")
    assert r._secret()


def test_real_secret_enables_board_in_http_mode(reload_routes):
    r = reload_routes(MEMAIX_TRANSPORT="http", HYDRA_SYSTEM_SECRET="a-real-32-byte-long-secret-value!")
    assert r._secret()


def test_disabled_board_rejects_cookies(reload_routes):
    r = reload_routes(MEMAIX_TRANSPORT="http", HYDRA_SYSTEM_SECRET=None, MEMAIX_ALLOW_DEV_SECRET=None)

    class _Req:
        cookies = {"memaix_board": "alice:20000:deadbeef"}

    assert r._check_cookie(_Req()) is None  # fail closed, no 500


# ------------------------------------------------------------------
# Per-user password binding
# ------------------------------------------------------------------


def test_shared_password_only_works_for_single_allowed_user(reload_routes):
    r = reload_routes(MEMAIX_ALLOWED_USERS="alice", MEMAIX_LOGIN_PASSWORD_HASH=_hash("pw"))
    assert r._verify_password("alice", "pw") is True


def test_shared_password_rejected_when_multiple_users(reload_routes):
    # With >1 allowed user, the shared hash must NOT authenticate anyone —
    # otherwise bob could log in as alice with the shared password.
    r = reload_routes(MEMAIX_ALLOWED_USERS="alice,bob", MEMAIX_LOGIN_PASSWORD_HASH=_hash("pw"))
    assert r._verify_password("alice", "pw") is False
    assert r._verify_password("bob", "pw") is False


def test_per_user_hashes_bind_password_to_user(reload_routes):
    r = reload_routes(
        MEMAIX_ALLOWED_USERS="alice,bob",
        MEMAIX_LOGIN_PASSWORD_HASH_ALICE=_hash("alice-pw"),
        MEMAIX_LOGIN_PASSWORD_HASH_BOB=_hash("bob-pw"),
    )
    assert r._verify_password("alice", "alice-pw") is True
    assert r._verify_password("bob", "bob-pw") is True
    # bob's password must not authenticate as alice
    assert r._verify_password("alice", "bob-pw") is False
    assert r._verify_password("bob", "alice-pw") is False


def test_no_hash_configured_denies(reload_routes):
    r = reload_routes(MEMAIX_ALLOWED_USERS="alice", MEMAIX_LOGIN_PASSWORD_HASH=None)
    assert r._verify_password("alice", "anything") is False
