# SPDX-License-Identifier: AGPL-3.0-or-later
"""Idempotency-key cache for write tools with external side effects.

docs/OPEN-GAPS.md #13: if the calling agent retries a tool call (e.g. after
a network glitch, unsure whether the first attempt landed), a tool that
talks to an external system (SMTP, CalDAV, Nextcloud) must not repeat the
side effect — a second email sent, a duplicate calendar event created.

A caller opts in by passing the same `idempotency_key` on retry. The first
call's result is cached per (user, tool, key); a retried call with the same
key returns the cached result without re-executing the tool. Only
successful results are cached — a failed attempt can be retried with the
same key to try again.

Scope: wired into server.py's `_audited` choke point for the tools whose
side effect is external and expensive to undo (email_send,
email_create_draft, calendar_create, calendar_update, nc_tasks_add) — see
FEATURE-* docs for the full write-tool inventory. Tools with a naturally
idempotent write (overwrite-by-path, upsert-by-id) or where a duplicate is
cheap/harmless (backlog_add) don't need this.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path


class IdempotencyStore:
    def __init__(self, db_path: Path) -> None:
        self._path = db_path
        self._lock = threading.Lock()
        self._init_db()

    @classmethod
    def for_path(cls, db_path: Path) -> "IdempotencyStore":
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
                CREATE TABLE IF NOT EXISTS idempotency_result (
                    memaix_user  TEXT NOT NULL,
                    tool         TEXT NOT NULL,
                    idem_key     TEXT NOT NULL,
                    result       TEXT NOT NULL,
                    created_at   TEXT NOT NULL,
                    PRIMARY KEY (memaix_user, tool, idem_key)
                )
                """
            )
            conn.commit()

    def get(self, user: str, tool: str, key: str) -> dict | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT result FROM idempotency_result WHERE memaix_user=? AND tool=? AND idem_key=?",
                (user, tool, key),
            ).fetchone()
        return json.loads(row["result"]) if row else None

    def record(self, user: str, tool: str, key: str, result: dict) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO idempotency_result
                   (memaix_user, tool, idem_key, result, created_at) VALUES (?, ?, ?, ?, ?)""",
                (user, tool, key, json.dumps(result), datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()

    def purge_older_than(self, cutoff_iso: str) -> None:
        """Housekeeping — nothing calls this automatically yet; an operator
        (or a future scheduled task) can use it to bound table growth."""
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM idempotency_result WHERE created_at < ?", (cutoff_iso,))
            conn.commit()
