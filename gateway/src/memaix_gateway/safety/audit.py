# SPDX-License-Identifier: AGPL-3.0-or-later
"""Append-only audit log persisted to SQLite.

The audit table lives in {vault}/.memaix.db (same file as MemoryStore)
so every vault has a co-located audit trail.  For gateway-level auditing
(not tied to a single vault), use AuditLog.for_path(db_path) with an
explicit path, e.g. from MEMAIX_AUDIT_DB.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path


class AuditLog:
    """Thread-safe audit logger, singleton per db_path."""

    _instances: dict[Path, "AuditLog"] = {}
    _class_lock = threading.Lock()

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path.resolve()
        self._lock = threading.Lock()
        self._conn = self._open_db()

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def for_vault(cls, vault: Path) -> "AuditLog":
        """Use (or create) an audit log sharing the vault's .memaix.db."""
        return cls._for_path((vault.resolve() / ".memaix.db"))

    @classmethod
    def for_path(cls, db_path: Path) -> "AuditLog":
        """Use (or create) an audit log at an explicit path."""
        return cls._for_path(db_path.resolve())

    @classmethod
    def _for_path(cls, db_path: Path) -> "AuditLog":
        with cls._class_lock:
            if db_path not in cls._instances:
                cls._instances[db_path] = cls(db_path)
            return cls._instances[db_path]

    @classmethod
    def _clear_instances(cls) -> None:
        """For testing only."""
        with cls._class_lock:
            cls._instances.clear()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _open_db(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit (
                id      INTEGER PRIMARY KEY,
                ts      TEXT NOT NULL,
                user    TEXT NOT NULL,
                project TEXT NOT NULL,
                tool    TEXT NOT NULL,
                ok      INTEGER NOT NULL,
                detail  TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.commit()
        return conn

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def log(
        self,
        user: str,
        project: str,
        tool: str,
        ok: bool,
        detail: str = "",
    ) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._conn.execute(
                "INSERT INTO audit (ts, user, project, tool, ok, detail)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (ts, user, project, tool, int(ok), detail),
            )
            self._conn.commit()

    def tail(self, limit: int = 50) -> list[dict]:
        """Return up to *limit* most-recent events, oldest first."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT ts, user, project, tool, ok, detail"
                " FROM audit ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                "ts": r["ts"],
                "user": r["user"],
                "project": r["project"],
                "tool": r["tool"],
                "ok": bool(r["ok"]),
                "detail": r["detail"],
            }
            for r in reversed(rows)
        ]

    def query(
        self,
        user: str | None = None,
        project: str | None = None,
        tool: str | None = None,
        ok: bool | None = None,
        since: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """Filtered query with optional WHERE clauses and pagination.

        All filter parameters are optional and combinable.
        Returns rows oldest-first within the matched set.
        """
        conditions: list[str] = []
        params: list = []
        if user is not None:
            conditions.append("user = ?")
            params.append(user)
        if project is not None:
            conditions.append("project = ?")
            params.append(project)
        if tool is not None:
            conditions.append("tool = ?")
            params.append(tool)
        if ok is not None:
            conditions.append("ok = ?")
            params.append(int(ok))
        if since is not None:
            conditions.append("ts >= ?")
            params.append(since)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        params.extend([limit, offset])

        with self._lock:
            rows = self._conn.execute(
                f"SELECT id, ts, user, project, tool, ok, detail"
                f" FROM audit {where} ORDER BY id DESC LIMIT ? OFFSET ?",
                params,
            ).fetchall()
        return [
            {
                "id": r["id"],
                "ts": r["ts"],
                "user": r["user"],
                "project": r["project"],
                "tool": r["tool"],
                "ok": bool(r["ok"]),
                "detail": r["detail"],
            }
            for r in reversed(rows)
        ]
