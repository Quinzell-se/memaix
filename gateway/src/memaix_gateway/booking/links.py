# SPDX-License-Identifier: AGPL-3.0-or-later
"""Public booking-link registry — memaix-src card 2bef1062.

Maps an opaque, unguessable slug to the (project, host user) it books
against. The slug IS the capability, the same convention rule_webhook uses
for its token (rules/match.py) — knowing it is enough to look up available
slots and attempt a booking, no login required. Provisioned by an operator
dropping a JSON file (config/booking_links/<slug>.json); no MCP tool
creates these yet — deliberately deferred until the booking epic needs
self-service link creation.
"""

from __future__ import annotations

import json
from pathlib import Path

from .. import config


def _links_dir() -> Path:
    d = config.CONFIG_DIR / "booking_links"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_link(slug: str) -> dict | None:
    """{"project", "user", "duration_min", "title_template"} for *slug*, or
    None if unknown. Never raises on missing/malformed slugs — callers
    treat both as a 404, not a 500."""
    if not slug or "/" in slug or ".." in slug:
        return None
    path = _links_dir() / f"{slug}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or not data.get("project") or not data.get("user"):
        return None
    return data
