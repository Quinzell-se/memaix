# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-event manual busy/free overrides — memaix-src backlog card c7698ff3.

Distinct from calendar_overrides.py's OverrideStore, which overrides
arbitrary [start, end) time windows with no source-event identity. This
store is keyed by provider-native event/series ids (calendar_cache.py's
per-event "events" list, card 4daa20e2/c7698ff3), letting a user click one
specific event — or its whole recurring series — and mark it Upptagen or
Tillgänglig regardless of what the source calendar said. Never written back
to any source calendar, by construction (same guarantee as OverrideStore).

Storage: one JSON file per (project, user) in the project vault, same
convention as every other calendar_* store in this package.
"""

from __future__ import annotations

import json
from pathlib import Path

from .aggregate import CalendarEvent

VALID_STATES = {"busy", "free"}


def _event_overrides_path(acl, project: str, user: str) -> Path:
    vault = acl.resource(project, "vault")
    if not vault:
        raise ValueError(f"project {project!r} has no vault configured")
    directory = Path(vault) / "calendar_event_overrides"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{user}.json"


class EventOverrideStore:
    """instances/series overrides, both nested {source: {id: entry}} —
    nesting under source avoids a same-id collision between two different
    calendar sources (a Google event id and a CalDAV UID are only unique
    within their own source)."""

    def __init__(self, acl, project: str, user: str) -> None:
        self._path = _event_overrides_path(acl, project, user)

    def _read(self) -> dict:
        if not self._path.exists():
            return {"instances": {}, "series": {}}
        return json.loads(self._path.read_text())

    def _write(self, data: dict) -> None:
        self._path.write_text(json.dumps(data))

    def list(self) -> dict:
        return self._read()

    def set_instance(self, source: str, uid: str, state: str, note: str = "") -> None:
        if state not in VALID_STATES:
            raise ValueError(f"invalid state {state!r}, must be one of {sorted(VALID_STATES)}")
        data = self._read()
        data["instances"].setdefault(source, {})[uid] = {"state": state, "note": note}
        self._write(data)

    def clear_instance(self, source: str, uid: str) -> bool:
        data = self._read()
        bucket = data["instances"].get(source, {})
        if uid not in bucket:
            return False
        del bucket[uid]
        self._write(data)
        return True

    def set_series(self, source: str, series_id: str, state: str, note: str = "") -> None:
        if state not in VALID_STATES:
            raise ValueError(f"invalid state {state!r}, must be one of {sorted(VALID_STATES)}")
        data = self._read()
        data["series"].setdefault(source, {})[series_id] = {"state": state, "note": note}
        self._write(data)

    def clear_series(self, source: str, series_id: str) -> bool:
        data = self._read()
        bucket = data["series"].get(source, {})
        if series_id not in bucket:
            return False
        del bucket[series_id]
        self._write(data)
        return True

    def resolve(self, event: CalendarEvent) -> str | None:
        """"busy" | "free" | None (no override, honor the source).

        Precedence: an instance-level override always wins — it's always an
        explicit click on that exact event, including on an exception
        instance. A series-level override applies to normal occurrences of
        that series, but NOT to an exception instance (one that broke out
        of the series, e.g. moved to a different time) — that instance must
        be overridden individually. This is the card's core decision
        (2026-09-04 14:35 UTC comment)."""
        data = self._read()
        inst = data["instances"].get(event.source, {}).get(event.uid)
        if inst is not None:
            return inst["state"]

        if event.series_id and not event.is_exception:
            ser = data["series"].get(event.source, {}).get(event.series_id)
            if ser is not None:
                return ser["state"]

        return None
