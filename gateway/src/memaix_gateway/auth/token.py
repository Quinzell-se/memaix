# SPDX-License-Identifier: AGPL-3.0-or-later
"""JWT token verification via Hydra / JWKS.

Implements the MCP SDK TokenVerifier protocol so that FastMCP's auth middleware
can call verify_token(raw_token) → AccessToken | None.
"""

from __future__ import annotations

import logging
from typing import Any

import jwt
from mcp.server.auth.provider import AccessToken

logger = logging.getLogger(__name__)


class AuthError(Exception):
    """Authentication / token-verification error."""


class HydraTokenVerifier:
    """Verify Bearer tokens against a JWKS endpoint (e.g. Ory Hydra).

    Implements the MCP SDK ``TokenVerifier`` protocol.
    """

    def __init__(self, jwks_uri: str, issuer: str) -> None:
        self._jwks_uri = jwks_uri
        self._issuer = issuer
        self._jwks_client = jwt.PyJWKClient(jwks_uri, cache_keys=True, lifespan=3600)

    async def verify_token(self, token: str) -> AccessToken | None:
        """Return an AccessToken if the JWT is valid, None on any error."""
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            claims: dict[str, Any] = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256", "ES256"],
                issuer=self._issuer,
                options={"verify_aud": False},
            )
        except Exception as exc:
            logger.debug("token verification failed: %s", exc)
            return None

        # Scopes — Hydra uses "scp" (list or space-separated string), fallback "scope".
        raw_scope = claims.get("scp", claims.get("scope", ""))
        if isinstance(raw_scope, str):
            scopes: list[str] = raw_scope.split() if raw_scope else []
        else:
            scopes = list(raw_scope)

        # Client identity — "azp" (authorised party) is the canonical Hydra field.
        client_id: str = (
            claims.get("azp")
            or claims.get("client_id")
            or claims.get("sub", "unknown")
        )

        return AccessToken(
            token=token,
            client_id=client_id,
            scopes=scopes,
            expires_at=claims.get("exp"),
            subject=claims.get("sub"),
            claims=claims,
        )

    @classmethod
    def from_config(cls, cfg: dict) -> "HydraTokenVerifier":
        """Construct from merged gateway config (brand/memaix/acl dict).

        Reads ``cfg["memaix"]["auth"]["issuer"]`` and derives the JWKS URI as
        ``{issuer}/.well-known/jwks.json``.
        """
        issuer: str = cfg["memaix"]["auth"]["issuer"]
        jwks_uri = f"{issuer}/.well-known/jwks.json"
        return cls(jwks_uri=jwks_uri, issuer=issuer)
