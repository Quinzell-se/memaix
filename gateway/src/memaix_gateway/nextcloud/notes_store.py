# SPDX-License-Identifier: AGPL-3.0-or-later
"""NotesLinkStore — persists which memory note is linked to which Nextcloud
Notes id, and when they were last synced (FEATURE-NEXTCLOUD-BACKEND.md §7).

Unlike backlog items (YAML frontmatter can carry `deck_card_id` directly),
memory notes are a plain content blob in MemoryStore with no metadata
slot — so the link + sync baseline live here instead, one small SQLite
table, same conventions as every other *Store in this codebase.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path


class NotesLinkStore:
    def __init__(self, db_path: Path) -> None:
        self._path = db_path
        self._lock = threading.Lock()
        self._init_db()

    @classmethod
    def for_path(cls, db_path: Path) -> "NotesLinkStore":
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
                CREATE TABLE IF NOT EXISTS notes_link (
                    project    TEXT NOT NULL,
                    note_path  TEXT NOT NULL,
                    nc_note_id TEXT NOT NULL,
                    synced_at  TEXT NOT NULL,
                    PRIMARY KEY (project, note_path)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_notes_link_nc ON notes_link(project, nc_note_id)"
            )
            conn.commit()

    def set_link(self, project: str, note_path: str, nc_note_id: str, synced_at: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """INSERT INTO notes_link (project, note_path, nc_note_id, synced_at) VALUES (?, ?, ?, ?)
                   ON CONFLICT(project, note_path) DO UPDATE SET
                     nc_note_id=excluded.nc_note_id, synced_at=excluded.synced_at""",
                (project, note_path, str(nc_note_id), synced_at),
            )
            conn.commit()

    def list_links(self, project: str) -> list[dict]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM notes_link WHERE project=?", (project,)
            ).fetchall()
        return [dict(r) for r in rows]
