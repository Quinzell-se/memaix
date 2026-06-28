"""Config loading — reads config/*.yaml and resolves *_ref against the environment.

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
    """Resolve a *_ref name to its value from the environment (.env)."""
    if not ref:
        return None
    val = os.environ.get(ref)
    if val is None:
        raise KeyError(f"secret ref not set in environment: {ref}")
    return val
