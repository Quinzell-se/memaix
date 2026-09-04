# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-user on/off switch for the meeting booker — memaix-src backlog card
9e035c73.

Off by default: a user who has never touched this setting must not have a
booking surface exposed to anyone. This module only stores the flag; it is
the consuming card's job (the public booking page, 2bef1062) to actually
refuse to serve a booking flow when disabled — kept separate the same way
calendar_free_busy explicitly defers its own fail-closed behavior to that
card rather than baking it in early.

Storage: one JSON file per (project, user) in the project vault, same
convention as working_hours.py and calendar_overrides.py.
"""

from __future__ import annotations

import json
from pathlib import Path


def _booking_settings_path(acl, project: str, user: str) -> Path:
    vault = acl.resource(project, "vault")
    if not vault:
        raise ValueError(f"project {project!r} has no vault configured")
    directory = Path(vault) / "booking_settings"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{user}.json"


class BookingSettingsStore:
    def __init__(self, acl, project: str, user: str) -> None:
        self._path = _booking_settings_path(acl, project, user)

    def get(self) -> dict:
        """{"enabled": False} if never configured — the booker is off until
        a user explicitly turns it on."""
        if not self._path.exists():
            return {"enabled": False}
        return json.loads(self._path.read_text())

    def set(self, enabled: bool) -> None:
        self._path.write_text(json.dumps({"enabled": bool(enabled)}))
