"""Config loading — reads config/*.yaml and resolves *_ref secrets.

A *_ref is a reference, never a value (see docs/SECRETS.md). It is resolved by prefix:
  env:NAME            -> environment variable NAME (.env)         [default if no prefix]
  file:/path          -> file contents (Docker/systemd secrets, tmpfs)
  vault:path#field    -> OpenBao/HashiCorp Vault   [todo: wire client at implementation]
  kms:id              -> cloud KMS / Secret Manager [todo: wire client at implementation]
A bare name without a prefix is treated as env: for backward compatibility.

SPDX-License-Identifier: AGPL-3.0-or-later
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

CONFIG_DIR = Path(os.environ.get("MEMAIX_CONFIG_DIR", "/app/config"))


def _load(name: str) -> dict:
    path = CONFIG_DIR / name
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def load() -> dict:
    """Return merged config: {brand, memaix, acl}."""
    return {
        "brand": _load("brand.yaml"),
        "memaix": _load("memaix.yaml"),
        "acl": _load("acl.yaml"),
    }


def secret(ref: str | None) -> str | None:
    """Resolve a *_ref to its value by prefix (see module docstring / docs/SECRETS.md).

    Never log the return value; never echo it to a client (docs/THREAT-MODEL.md).
    """
    if not ref:
        return None

    scheme, _, rest = ref.partition(":")
    if not rest:  # bare name → env (backward compatible)
        scheme, rest = "env", ref

    if scheme == "env":
        val = os.environ.get(rest)
        if val is None:
            raise KeyError(f"secret ref not set in environment: {rest}")
        return val

    if scheme == "file":
        path = Path(rest)
        if not path.exists():
            raise KeyError(f"secret file not found: {rest}")
        return path.read_text().strip()

    if scheme in ("vault", "kms"):
        # TODO: wire OpenBao/Vault or cloud-KMS client at implementation (docs/SECRETS.md).
        raise NotImplementedError(f"secret backend not yet wired: {scheme}")

    raise ValueError(f"unknown secret ref scheme: {scheme!r} (use env:/file:/vault:/kms:)")
