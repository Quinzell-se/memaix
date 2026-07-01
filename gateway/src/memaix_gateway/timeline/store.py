# SPDX-License-Identifier: AGPL-3.0-or-later
"""ActionsStore — SQLite-backed log of reversible actions + their undo state.

See docs/FEATURE-UNDO-TIMELINE.md. Same SQLite conventions as the rest of the
gateway (WAL mode, a single threading.Lock, a fresh connection per operation).
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path


class ActionsStore:
    def __init__(self, db_path: Path) -> None:
        self._path = db_path
        self._lock = threading.Lock()
        self._init_db()

    @classmethod
    def for_path(cls, db_path: Path) -> "ActionsStore":
        return cls(db_path)

    def _connect(self) -> sqlite3.Connection:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS actions (
                    id             TEXT PRIMARY KEY,
                    memaix_user    TEXT NOT NULL,
                    project        TEXT NOT NULL,
                    tool           TEXT NOT NULL,
                    summary        TEXT NOT NULL,
                    reversible     INTEGER NOT NULL,
                    inverse_json   TEXT,
                    status         TEXT NOT NULL DEFAULT 'done',
                    created_at     TEXT NOT NULL,
                    undone_at      TEXT,
                    undo_of        TEXT,
                    undo_action_id TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_actions_scope ON actions(project, created_at)"
            )
            conn.commit()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _row_to_dict(self, row: sqlite3.Row) -> dict:
        d = dict(row)
        inverse_json = d.pop("inverse_json")
        d["inverse"] = json.loads(inverse_json) if inverse_json else None
        d["reversible"] = bool(d["reversible"])
        return d

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record(
        self,
        user: str,
        project: str,
        tool: str,
        summary: str,
        inverse: dict | None,
        *,
        undo_of: str | None = None,
    ) -> str:
        action_id = uuid.uuid4().hex
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO actions
                    (id, memaix_user, project, tool, summary, reversible,
                     inverse_json, status, created_at, undo_of)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'done', ?, ?)
                """,
                (
                    action_id, user, project, tool, summary,
                    1 if inverse else 0,
                    json.dumps(inverse) if inverse else None,
                    self._now(),
                    undo_of,
                ),
            )
            conn.commit()
        return action_id

    def get(self, action_id: str) -> dict | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM actions WHERE id=?", (action_id,)).fetchone()
        return self._row_to_dict(row) if row else None

    def list(self, projects: list[str], limit: int = 50) -> list[dict]:
        if not projects:
            return []
        with self._lock, self._connect() as conn:
            placeholders = ",".join("?" for _ in projects)
            rows = conn.execute(
                f"SELECT * FROM actions WHERE project IN ({placeholders}) "
                "ORDER BY created_at DESC LIMIT ?",
                (*projects, limit),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def claim_undo(self, action_id: str) -> dict | None:
        """Atomically move a 'done' reversible action to 'undone'.

        Returns the pre-claim row (still holding status='done' semantics for
        the caller to act on) if the claim succeeded, or None if the action
        doesn't exist, isn't reversible, or was already undone/is undoing.
        """
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM actions WHERE id=?", (action_id,)).fetchone()
            if row is None or not row["reversible"] or row["status"] != "done":
                return None
            cur = conn.execute(
                "UPDATE actions SET status='undone', undone_at=? WHERE id=? AND status='done'",
                (self._now(), action_id),
            )
            conn.commit()
            if cur.rowcount == 0:
                return None
        return self._row_to_dict(row)

    def mark_undo_failed(self, action_id: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE actions SET status='undo_failed' WHERE id=?", (action_id,)
            )
            conn.commit()

    def link_undo(self, original_id: str, undo_action_id: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE actions SET undo_action_id=? WHERE id=?",
                (undo_action_id, original_id),
            )
            conn.commit()

    def purge_older_than(self, cutoff_iso: str) -> int:
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM actions WHERE created_at < ?", (cutoff_iso,))
            conn.commit()
            return cur.rowcount
