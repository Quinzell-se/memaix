# SPDX-License-Identifier: AGPL-3.0-or-later
"""RulesStore — automation rules, their run log, and standing instructions.

See docs/FEATURE-AUTOMATION-RULES.md §4.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path


class RulesStore:
    def __init__(self, db_path: Path) -> None:
        self._path = db_path
        self._lock = threading.Lock()
        self._init_db()

    @classmethod
    def for_path(cls, db_path: Path) -> "RulesStore":
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
                CREATE TABLE IF NOT EXISTS rules (
                    id          TEXT PRIMARY KEY,
                    memaix_user TEXT NOT NULL,
                    project     TEXT NOT NULL,
                    name        TEXT NOT NULL,
                    enabled     INTEGER NOT NULL DEFAULT 1,
                    trigger     TEXT NOT NULL,
                    conditions  TEXT NOT NULL DEFAULT '[]',
                    actions     TEXT NOT NULL,
                    created_at  TEXT NOT NULL,
                    updated_at  TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rule_runs (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    rule_id    TEXT NOT NULL,
                    event_key  TEXT NOT NULL,
                    ran_at     TEXT NOT NULL,
                    ok         INTEGER NOT NULL,
                    detail     TEXT NOT NULL DEFAULT '',
                    UNIQUE(rule_id, event_key)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS standing_instructions (
                    memaix_user TEXT PRIMARY KEY,
                    text        TEXT NOT NULL,
                    updated_at  TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # ------------------------------------------------------------------
    # Rules CRUD
    # ------------------------------------------------------------------

    def _row_to_rule(self, row: sqlite3.Row) -> dict:
        d = dict(row)
        d["enabled"] = bool(d["enabled"])
        d["trigger"] = json.loads(d["trigger"])
        d["conditions"] = json.loads(d["conditions"])
        d["actions"] = json.loads(d["actions"])
        return d

    def add_rule(
        self, user: str, project: str, name: str, trigger: dict,
        actions: list[dict], conditions: list[dict] | None = None,
    ) -> dict:
        rule_id = uuid.uuid4().hex
        now = self._now()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO rules
                    (id, memaix_user, project, name, enabled, trigger,
                     conditions, actions, created_at, updated_at)
                VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
                """,
                (
                    rule_id, user, project, name, json.dumps(trigger),
                    json.dumps(conditions or []), json.dumps(actions), now, now,
                ),
            )
            conn.commit()
        rule = self.get_rule(rule_id)
        assert rule is not None  # just inserted under the same id
        return rule

    def get_rule(self, rule_id: str) -> dict | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM rules WHERE id=?", (rule_id,)).fetchone()
        return self._row_to_rule(row) if row else None

    def list_rules(self, projects: list[str] | None = None, enabled_only: bool = False) -> list[dict]:
        with self._lock, self._connect() as conn:
            if projects:
                placeholders = ",".join("?" for _ in projects)
                sql = f"SELECT * FROM rules WHERE project IN ({placeholders})"  # nosec B608 -- placeholders is a "?,?,..." count string, values are bound below
                params: list = list(projects)
            else:
                sql = "SELECT * FROM rules WHERE 1=1"
                params = []
            if enabled_only:
                sql += " AND enabled=1"
            sql += " ORDER BY created_at DESC"
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_rule(r) for r in rows]

    def set_enabled(self, rule_id: str, enabled: bool) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "UPDATE rules SET enabled=?, updated_at=? WHERE id=?",
                (1 if enabled else 0, self._now(), rule_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def delete_rule(self, rule_id: str) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM rules WHERE id=?", (rule_id,))
            conn.commit()
            return cur.rowcount > 0

    # ------------------------------------------------------------------
    # Dedupe / run log
    # ------------------------------------------------------------------

    def try_reserve(self, rule_id: str, event_key: str) -> bool:
        """Atomically claim (rule_id, event_key). True the first time, False
        on any repeat — this is the idempotency guard against a rule firing
        twice for the same underlying event (retry, mail-poll overlap, ...)."""
        with self._lock, self._connect() as conn:
            try:
                conn.execute(
                    "INSERT INTO rule_runs (rule_id, event_key, ran_at, ok) VALUES (?, ?, ?, 1)",
                    (rule_id, event_key, self._now()),
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def record_run_detail(self, rule_id: str, event_key: str, ok: bool, detail: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE rule_runs SET ok=?, detail=? WHERE rule_id=? AND event_key=?",
                (1 if ok else 0, detail, rule_id, event_key),
            )
            conn.commit()

    def list_runs(self, rule_id: str, limit: int = 20) -> list[dict]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM rule_runs WHERE rule_id=? ORDER BY id DESC LIMIT ?",
                (rule_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Standing instructions
    # ------------------------------------------------------------------

    def set_standing(self, user: str, text: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO standing_instructions (memaix_user, text, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(memaix_user) DO UPDATE SET text=excluded.text, updated_at=excluded.updated_at
                """,
                (user, text, self._now()),
            )
            conn.commit()

    def get_standing(self, user: str) -> str | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT text FROM standing_instructions WHERE memaix_user=?", (user,)
            ).fetchone()
        return row["text"] if row else None
