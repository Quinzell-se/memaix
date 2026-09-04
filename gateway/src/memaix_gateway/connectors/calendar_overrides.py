# SPDX-License-Identifier: AGPL-3.0-or-later
"""Host-owned calendar overrides — memaix-src backlog card 4daa20e2.

A host can mark extra busy time (e.g. "block me Friday afternoon") or mark
a source-busy block as actually free (e.g. an all-day "working from the
cabin" event that shouldn't block bookings). Overrides are applied ONLY at
read time, on top of the synced cache (calendar_cache.py) — they are never
written back to any external calendar source, by construction: this store
holds no reference to any adapter's write methods.

Storage: one JSON file per (project, user) in the project vault, same
convention as calendar_cache.py's cache file.

Explicitly out of scope here (memaix-src card c7698ff3, not this one):
whether an override is a one-shot window or a recurring/standing rule.
Entries below are concrete [start, end) windows only — nothing in this
shape blocks a later `rule`/recurrence field being added.
"""

from __future__ import annotations

import json
from pathlib import Path

from .aggregate import BusyInterval, merge_busy, to_utc


def _overrides_path(acl, project: str, user: str) -> Path:
    vault = acl.resource(project, "vault")
    if not vault:
        raise ValueError(f"project {project!r} has no vault configured")
    directory = Path(vault) / "calendar_overrides"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{user}.json"


class OverrideStore:
    def __init__(self, acl, project: str, user: str) -> None:
        self._path = _overrides_path(acl, project, user)

    def _read(self) -> dict:
        if not self._path.exists():
            return {"busy": [], "free": []}
        return json.loads(self._path.read_text())

    def _write(self, data: dict) -> None:
        self._path.write_text(json.dumps(data))

    def add_busy(self, start, end, note: str = "") -> None:
        data = self._read()
        data["busy"].append({"start": to_utc(start).isoformat(), "end": to_utc(end).isoformat(), "note": note})
        self._write(data)

    def add_free(self, start, end, note: str = "") -> None:
        data = self._read()
        data["free"].append({"start": to_utc(start).isoformat(), "end": to_utc(end).isoformat(), "note": note})
        self._write(data)

    def list(self) -> dict:
        return self._read()

    def remove(self, kind: str, index: int) -> bool:
        data = self._read()
        entries = data.get(kind, [])
        if 0 <= index < len(entries):
            entries.pop(index)
            self._write(data)
            return True
        return False

    def apply(self, busy: list[BusyInterval]) -> list[BusyInterval]:
        """Union the stored busy overrides in (merged like any other
        source), then subtract the stored free overrides — subtraction can
        split one busy block into two."""
        data = self._read()
        combined = merge_busy(
            list(busy)
            + [
                BusyInterval(to_utc(o["start"]), to_utc(o["end"]), "override:busy")
                for o in data.get("busy", [])
            ]
        )

        for o in data.get("free", []):
            free_start, free_end = to_utc(o["start"]), to_utc(o["end"])
            next_combined: list[BusyInterval] = []
            for iv in combined:
                if free_end <= iv.start or free_start >= iv.end:
                    next_combined.append(iv)
                    continue
                if free_start > iv.start:
                    next_combined.append(BusyInterval(iv.start, free_start, iv.source))
                if free_end < iv.end:
                    next_combined.append(BusyInterval(free_end, iv.end, iv.source))
            combined = next_combined

        return sorted(combined)
