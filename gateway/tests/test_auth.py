# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for HydraTokenVerifier — all network calls are mocked."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import jwt
import pytest

from memaix_gateway.auth.token import AuthError, HydraTokenVerifier


JWKS_URI = "https://hydra.example.com/.well-known/jwks.json"
ISSUER = "https://hydra.example.com"


def _run(coro):
    """Helper: run a coroutine synchronously."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@patch("jwt.decode")
@patch.object(jwt.PyJWKClient, "get_signing_key_from_jwt")
def test_valid_token_returns_access_token(mock_get_key, mock_decode):
    mock_get_key.return_value = MagicMock(key="signing-key")
    mock_decode.return_value = {
        "sub": "user123",
        "azp": "client456",
        "scp": "read write",
        "exp": 9_999_999_999,
        "iss": ISSUER,
    }

    verifier = HydraTokenVerifier(JWKS_URI, ISSUER)
    result = _run(verifier.verify_token("fake.jwt.token"))

    assert result is not None
    assert result.subject == "user123"
    assert result.client_id == "client456"
    assert "read" in result.scopes
    assert "write" in result.scopes
    assert result.expires_at == 9_999_999_999
    assert result.token == "fake.jwt.token"


@patch("jwt.decode")
@patch.object(jwt.PyJWKClient, "get_signing_key_from_jwt")
def test_scopes_as_list(mock_get_key, mock_decode):
    """scp can be a list (not just a space-separated string)."""
    mock_get_key.return_value = MagicMock(key="key")
    mock_decode.return_value = {
        "sub": "u1",
        "azp": "c1",
        "scp": ["admin", "read"],
        "exp": 9_999_999_999,
    }

    verifier = HydraTokenVerifier(JWKS_URI, ISSUER)
    result = _run(verifier.verify_token("tok"))

    assert result is not None
    assert "admin" in result.scopes
    assert "read" in result.scopes


@patch("jwt.decode")
@patch.object(jwt.PyJWKClient, "get_signing_key_from_jwt")
def test_client_id_fallback_to_client_id_claim(mock_get_key, mock_decode):
    """Falls back to 'client_id' claim when 'azp' is absent."""
    mock_get_key.return_value = MagicMock(key="key")
    mock_decode.return_value = {
        "sub": "u1",
        "client_id": "fallback_client",
        "scp": "",
        "exp": 9_999_999_999,
    }

    verifier = HydraTokenVerifier(JWKS_URI, ISSUER)
    result = _run(verifier.verify_token("tok"))

    assert result is not None
    assert result.client_id == "fallback_client"


@patch("jwt.decode")
@patch.object(jwt.PyJWKClient, "get_signing_key_from_jwt")
def test_client_id_fallback_to_sub(mock_get_key, mock_decode):
    """Falls back to 'sub' when both 'azp' and 'client_id' are absent."""
    mock_get_key.return_value = MagicMock(key="key")
    mock_decode.return_value = {
        "sub": "sub_as_client",
        "scp": "",
        "exp": 9_999_999_999,
    }

    verifier = HydraTokenVerifier(JWKS_URI, ISSUER)
    result = _run(verifier.verify_token("tok"))

    assert result is not None
    assert result.client_id == "sub_as_client"


# ---------------------------------------------------------------------------
# Error cases — must return None, not raise
# ---------------------------------------------------------------------------


@patch("jwt.decode")
@patch.object(jwt.PyJWKClient, "get_signing_key_from_jwt")
def test_expired_token_returns_none(mock_get_key, mock_decode):
    mock_get_key.return_value = MagicMock(key="key")
    mock_decode.side_effect = jwt.ExpiredSignatureError("token expired")

    verifier = HydraTokenVerifier(JWKS_URI, ISSUER)
    result = _run(verifier.verify_token("expired.jwt.token"))

    assert result is None


@patch.object(jwt.PyJWKClient, "get_signing_key_from_jwt")
def test_bad_signature_returns_none(mock_get_key):
    mock_get_key.side_effect = jwt.InvalidSignatureError("bad signature")

    verifier = HydraTokenVerifier(JWKS_URI, ISSUER)
    result = _run(verifier.verify_token("tampered.jwt.token"))

    assert result is None


@patch.object(jwt.PyJWKClient, "get_signing_key_from_jwt")
def test_malformed_token_returns_none(mock_get_key):
    mock_get_key.side_effect = jwt.DecodeError("not a jwt")

    verifier = HydraTokenVerifier(JWKS_URI, ISSUER)
    result = _run(verifier.verify_token("not-a-jwt"))

    assert result is None


@patch("jwt.decode")
@patch.object(jwt.PyJWKClient, "get_signing_key_from_jwt")
def test_invalid_issuer_returns_none(mock_get_key, mock_decode):
    mock_get_key.return_value = MagicMock(key="key")
    mock_decode.side_effect = jwt.InvalidIssuerError("wrong issuer")

    verifier = HydraTokenVerifier(JWKS_URI, ISSUER)
    result = _run(verifier.verify_token("fake.jwt.token"))

    assert result is None


# ---------------------------------------------------------------------------
# from_config
# ---------------------------------------------------------------------------


def test_from_config_builds_correct_jwks_uri():
    cfg = {
        "memaix": {
            "auth": {
                "issuer": "https://auth.example.com",
            }
        }
    }
    verifier = HydraTokenVerifier.from_config(cfg)
    assert verifier._jwks_uri == "https://auth.example.com/.well-known/jwks.json"
    assert verifier._issuer == "https://auth.example.com"


def test_from_config_missing_issuer_raises():
    with pytest.raises(KeyError):
        HydraTokenVerifier.from_config({"memaix": {"auth": {}}})


# ---------------------------------------------------------------------------
# AuthError is importable
# ---------------------------------------------------------------------------


def test_auth_error_is_exception():
    err = AuthError("something went wrong")
    assert isinstance(err, Exception)
    assert str(err) == "something went wrong"
