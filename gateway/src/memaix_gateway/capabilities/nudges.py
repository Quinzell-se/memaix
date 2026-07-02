# SPDX-License-Identifier: AGPL-3.0-or-later
"""Contextual nudges — a sparse, rate-limited "you could also..." suggestion
after a tool call. See docs/FEATURE-DISCOVERABILITY.md §7.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

# last_tool -> capability key worth suggesting next. Deliberately small and
# hand-curated — a nudge should feel like an obvious next step, not noise.
_RULES: dict[str, str] = {
    "email_create_draft": "calendar.manage",
    "backlog_add": "pm.sprint_plan",
    "memory_write": "search.ask",
    "calendar_create": "brief.daily",
}


class NudgeState:
    """Tracks the last time a user was nudged, so suggestions stay sparse."""

    def __init__(self, db_path: Path) -> None:
        self._path = db_path
        self._lock = threading.Lock()
        self._init_db()

    @classmethod
    def for_path(cls, db_path: Path) -> "NudgeState":
        return cls(db_path)

    def _connect(self) -> sqlite3.Connection:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._path))
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS nudge_state (memaix_user TEXT PRIMARY KEY, last_ts REAL NOT NULL)"
            )
            conn.commit()

    def get_last(self, user: str) -> float | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT last_ts FROM nudge_state WHERE memaix_user=?", (user,)
            ).fetchone()
        return row[0] if row else None

    def set_last(self, user: str, ts: float) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO nudge_state (memaix_user, last_ts) VALUES (?, ?) "
                "ON CONFLICT(memaix_user) DO UPDATE SET last_ts=excluded.last_ts",
                (user, ts),
            )
            conn.commit()


def suggest(
    user: str, last_tool: str, available: list, state: NudgeState, *, now: float, min_gap_h: float = 6,
) -> dict | None:
    """Return {"capability_key", "title_key"} or None.

    Never suggests a locked (unavailable) capability, and never fires more
    than once per min_gap_h hours per user.
    """
    target_key = _RULES.get(last_tool)
    if not target_key:
        return None

    match = next((c for c in available if c.key == target_key), None)
    if match is None:
        return None  # locked or not registered — don't suggest the unusable

    last_ts = state.get_last(user)
    if last_ts is not None and (now - last_ts) < min_gap_h * 3600:
        return None

    state.set_last(user, now)
    return {"capability_key": match.key, "title_key": match.title_key}
