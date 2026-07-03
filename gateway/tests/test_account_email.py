# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for _get_account_email / _decode_id_token_claims (server.py).

Verifies that linking a second Google/Microsoft account no longer collides
under a shared 'linked-<provider>' key (see DEVELOPMENT-PROPOSALS.md §7).
"""

from __future__ import annotations

import jwt

from memaix_gateway.server import _decode_id_token_claims, _get_account_email


def _make_id_token(claims: dict) -> str:
    # Signature is irrelevant — decoding happens with verify_signature=False.
    return jwt.encode(claims, "unused-secret", algorithm="HS256")


def test_decode_id_token_claims_roundtrip():
    token = _make_id_token({"email": "alice@example.com", "sub": "123"})
    claims = _decode_id_token_claims(token)
    assert claims["email"] == "alice@example.com"
    assert claims["sub"] == "123"


def test_decode_id_token_claims_invalid_returns_empty():
    assert _decode_id_token_claims("not-a-jwt") == {}


def test_get_account_email_prefers_id_token_email():
    token_data = {
        "access_token": "x",
        "id_token": _make_id_token({"email": "bob@example.com", "sub": "u1"}),
    }
    assert _get_account_email("google", token_data) == "bob@example.com"


def test_get_account_email_falls_back_to_sub():
    token_data = {"id_token": _make_id_token({"sub": "u42"})}
    assert _get_account_email("google", token_data) == "google-u42"


def test_get_account_email_falls_back_to_placeholder():
    assert _get_account_email("google", {}) == "linked-google"


def test_get_account_email_two_accounts_do_not_collide():
    first = _get_account_email(
        "google", {"id_token": _make_id_token({"email": "a@example.com"})}
    )
    second = _get_account_email(
        "google", {"id_token": _make_id_token({"email": "b@example.com"})}
    )
    assert first != second


def test_get_account_email_microsoft_upn_fallback():
    token_data = {"id_token": _make_id_token({"preferred_username": "carol@corp.example"})}
    assert _get_account_email("microsoft", token_data) == "carol@corp.example"
