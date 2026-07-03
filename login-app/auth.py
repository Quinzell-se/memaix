# SPDX-License-Identifier: AGPL-3.0-or-later
"""Password verification for the Hydra login app — pure, dependency-light.

Kept free of FastAPI/requests imports so the security-critical logic can be
unit-tested from the gateway test suite without pulling the web stack.

Security invariant (impersonation defence): this app mints an OAuth identity
with subject=username, so a *shared* password that could authenticate any user
would let one password-holder log in AS a different allowed user. The shared
hash is therefore honoured ONLY when exactly one user is allowed. Per-user
hashes come from two converging conventions — acl.yaml (`users.<id>.
password_hash`) and the env var `MEMAIX_LOGIN_PASSWORD_HASH_<USER>` (the same
convention the board UI uses) — with the env taking precedence.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from collections.abc import Iterable, Mapping


def pbkdf2_check(provided: str, stored_hash: str) -> bool:
    """Constant-time PBKDF2-HMAC-SHA256 check. Format: salt_hex:key_hex."""
    if not stored_hash or ":" not in stored_hash:
        return False
    salt_hex, key_hex = stored_hash.split(":", 1)
    try:
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    derived = hashlib.pbkdf2_hmac("sha256", provided.encode(), salt, 200_000)
    return hmac.compare_digest(derived.hex(), key_hex)


def load_per_user_hashes(acl_path: str) -> dict[str, str]:
    """Read per-user password hashes from acl.yaml (users.<id>.password_hash).

    Returns {} if the file is missing or unparseable — callers fall back to
    the env/shared conventions.
    """
    hashes: dict[str, str] = {}
    try:
        import yaml

        with open(acl_path) as f:
            acl = yaml.safe_load(f) or {}
        for uid, udata in (acl.get("users") or {}).items():
            h = (udata or {}).get("password_hash", "")
            if h:
                hashes[uid] = h
    except Exception:
        pass  # acl.yaml missing or unparseable — fall back to shared hash
    return hashes


def password_hash_for(
    user: str,
    *,
    allowed_users: Iterable[str],
    per_user_hashes: Mapping[str, str],
    shared_hash: str,
    env: Mapping[str, str] | None = None,
) -> str:
    """Resolve the password hash for *user*, or "" if none applies.

    Precedence: env `MEMAIX_LOGIN_PASSWORD_HASH_<USER>` → acl.yaml per-user →
    shared hash (only when exactly one user is allowed).
    """
    environ = env if env is not None else os.environ
    env_per_user = environ.get(f"MEMAIX_LOGIN_PASSWORD_HASH_{user.upper()}")
    if env_per_user:
        return env_per_user
    acl_per_user = per_user_hashes.get(user)
    if acl_per_user:
        return acl_per_user
    if len(set(allowed_users)) == 1:
        return shared_hash
    return ""


def verify_password(
    user: str,
    provided: str,
    *,
    allowed_users: Iterable[str],
    per_user_hashes: Mapping[str, str],
    shared_hash: str,
    env: Mapping[str, str] | None = None,
) -> bool:
    return pbkdf2_check(
        provided,
        password_hash_for(
            user,
            allowed_users=allowed_users,
            per_user_hashes=per_user_hashes,
            shared_hash=shared_hash,
            env=env,
        ),
    )
