# SPDX-License-Identifier: AGPL-3.0-or-later
"""PMStore — SQLite persistence for the planning engine's schema
(docs/PM-DATA-MODEL.md). Base facts (resource/skill/task/dependency/
milestone) are shared; plan output (allocation/schedule) is per scenario.

This module is pure CRUD + the one non-trivial invariant the schema itself
can't enforce: `dependency` must stay a DAG (add_dependency rejects a cycle).
The engine (schedule.py/allocate.py/report.py) reads/writes through this
store; it never touches sqlite3 directly.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path


class CyclicDependencyError(ValueError):
    pass


class PMStore:
    def __init__(self, db_path: Path) -> None:
        self._path = db_path
        self._lock = threading.Lock()
        self._init_db()

    @classmethod
    def for_path(cls, db_path: Path) -> "PMStore":
        return cls(db_path)

    def _connect(self) -> sqlite3.Connection:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS resource (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project TEXT NOT NULL,
                    name TEXT NOT NULL,
                    user_sub TEXT,
                    cost_per_hour REAL,
                    capacity_hours_per_day REAL NOT NULL DEFAULT 8,
                    active INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS skill (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project TEXT NOT NULL,
                    name TEXT NOT NULL,
                    UNIQUE(project, name)
                );
                CREATE TABLE IF NOT EXISTS resource_skill (
                    resource_id INTEGER NOT NULL REFERENCES resource(id),
                    skill_id INTEGER NOT NULL REFERENCES skill(id),
                    level INTEGER,
                    PRIMARY KEY (resource_id, skill_id)
                );
                CREATE TABLE IF NOT EXISTS availability (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    resource_id INTEGER NOT NULL REFERENCES resource(id),
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    hours_per_day REAL NOT NULL,
                    reason TEXT
                );
                CREATE TABLE IF NOT EXISTS milestone (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project TEXT NOT NULL,
                    name TEXT NOT NULL,
                    target_date TEXT,
                    status TEXT NOT NULL DEFAULT 'open'
                );
                CREATE TABLE IF NOT EXISTS task (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project TEXT NOT NULL,
                    backlog_id TEXT,
                    title TEXT NOT NULL,
                    estimate_hours REAL,
                    required_skill_id INTEGER REFERENCES skill(id),
                    priority INTEGER NOT NULL DEFAULT 3,
                    milestone_id INTEGER REFERENCES milestone(id),
                    status TEXT NOT NULL DEFAULT 'todo',
                    percent_complete REAL NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS dependency (
                    predecessor_id INTEGER NOT NULL REFERENCES task(id),
                    successor_id INTEGER NOT NULL REFERENCES task(id),
                    type TEXT NOT NULL DEFAULT 'FS',
                    lag_days REAL NOT NULL DEFAULT 0,
                    PRIMARY KEY (predecessor_id, successor_id)
                );
                CREATE TABLE IF NOT EXISTS scenario (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project TEXT NOT NULL,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    parent_id INTEGER REFERENCES scenario(id),
                    created TEXT NOT NULL,
                    committed_by TEXT,
                    note TEXT
                );
                CREATE TABLE IF NOT EXISTS scenario_change (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scenario_id INTEGER NOT NULL REFERENCES scenario(id),
                    entity TEXT NOT NULL,
                    entity_id INTEGER NOT NULL,
                    field TEXT NOT NULL,
                    value TEXT
                );
                CREATE TABLE IF NOT EXISTS allocation (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scenario_id INTEGER NOT NULL REFERENCES scenario(id),
                    task_id INTEGER NOT NULL REFERENCES task(id),
                    resource_id INTEGER NOT NULL REFERENCES resource(id),
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    hours REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS schedule (
                    scenario_id INTEGER NOT NULL REFERENCES scenario(id),
                    task_id INTEGER NOT NULL REFERENCES task(id),
                    earliest_start TEXT, earliest_finish TEXT,
                    latest_start TEXT, latest_finish TEXT,
                    slack_days REAL, is_critical INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (scenario_id, task_id)
                );
                CREATE TABLE IF NOT EXISTS actual (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL REFERENCES task(id),
                    date TEXT NOT NULL,
                    hours_logged REAL,
                    percent_complete REAL,
                    note TEXT
                );
                CREATE INDEX IF NOT EXISTS ix_task_project ON task(project);
                CREATE INDEX IF NOT EXISTS ix_alloc_scn ON allocation(scenario_id);
                CREATE INDEX IF NOT EXISTS ix_sched_scn ON schedule(scenario_id);
                CREATE INDEX IF NOT EXISTS ix_actual_task ON actual(task_id);
                """
            )
            conn.commit()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # ------------------------------------------------------------------
    # Resources / skills / availability
    # ------------------------------------------------------------------

    def add_resource(
        self, project: str, name: str, *, user_sub: str | None = None,
        cost_per_hour: float | None = None, capacity_hours_per_day: float = 8.0,
        active: bool = True,
    ) -> dict:
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO resource (project, name, user_sub, cost_per_hour, capacity_hours_per_day, active)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (project, name, user_sub, cost_per_hour, capacity_hours_per_day, 1 if active else 0),
            )
            conn.commit()
            resource_id = cur.lastrowid
        assert resource_id is not None
        resource = self.get_resource(resource_id)
        assert resource is not None  # just inserted
        return resource

    def get_resource(self, resource_id: int) -> dict | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM resource WHERE id=?", (resource_id,)).fetchone()
        return self._row_to_resource(row) if row else None

    def _row_to_resource(self, row: sqlite3.Row) -> dict:
        d = dict(row)
        d["active"] = bool(d["active"])
        return d

    def list_resources(self, project: str, *, active_only: bool = False) -> list[dict]:
        sql = "SELECT * FROM resource WHERE project=?"
        params: list = [project]
        if active_only:
            sql += " AND active=1"
        sql += " ORDER BY id"
        with self._lock, self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_resource(r) for r in rows]

    def get_or_create_skill(self, project: str, name: str) -> dict:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM skill WHERE project=? AND name=?", (project, name)).fetchone()
            if row:
                return dict(row)
            cur = conn.execute("INSERT INTO skill (project, name) VALUES (?, ?)", (project, name))
            conn.commit()
            skill_id = cur.lastrowid
        return {"id": skill_id, "project": project, "name": name}

    def list_skills(self, project: str) -> list[dict]:
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT * FROM skill WHERE project=? ORDER BY name", (project,)).fetchall()
        return [dict(r) for r in rows]

    def set_resource_skill(self, resource_id: int, skill_id: int, level: int | None = None) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """INSERT INTO resource_skill (resource_id, skill_id, level) VALUES (?, ?, ?)
                   ON CONFLICT(resource_id, skill_id) DO UPDATE SET level=excluded.level""",
                (resource_id, skill_id, level),
            )
            conn.commit()

    def list_resource_skill_ids(self, resource_id: int) -> set[int]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT skill_id FROM resource_skill WHERE resource_id=?", (resource_id,)
            ).fetchall()
        return {r["skill_id"] for r in rows}

    def add_availability(
        self, resource_id: int, start_date: str, end_date: str, hours_per_day: float,
        reason: str | None = None,
    ) -> dict:
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO availability (resource_id, start_date, end_date, hours_per_day, reason)
                   VALUES (?, ?, ?, ?, ?)""",
                (resource_id, start_date, end_date, hours_per_day, reason),
            )
            conn.commit()
            row_id = cur.lastrowid
        return {"id": row_id, "resource_id": resource_id, "start_date": start_date,
                "end_date": end_date, "hours_per_day": hours_per_day, "reason": reason}

    def list_availability(self, resource_id: int) -> list[dict]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM availability WHERE resource_id=? ORDER BY start_date", (resource_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Milestones / tasks / dependencies
    # ------------------------------------------------------------------

    def add_milestone(self, project: str, name: str, target_date: str | None = None, status: str = "open") -> dict:
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO milestone (project, name, target_date, status) VALUES (?, ?, ?, ?)",
                (project, name, target_date, status),
            )
            conn.commit()
            milestone_id = cur.lastrowid
        return {"id": milestone_id, "project": project, "name": name, "target_date": target_date, "status": status}

    def list_milestones(self, project: str) -> list[dict]:
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT * FROM milestone WHERE project=? ORDER BY id", (project,)).fetchall()
        return [dict(r) for r in rows]

    def add_task(
        self, project: str, title: str, *, backlog_id: str | None = None,
        estimate_hours: float | None = None, required_skill_id: int | None = None,
        priority: int = 3, milestone_id: int | None = None, status: str = "todo",
        percent_complete: float = 0.0,
    ) -> dict:
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO task
                    (project, backlog_id, title, estimate_hours, required_skill_id,
                     priority, milestone_id, status, percent_complete)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (project, backlog_id, title, estimate_hours, required_skill_id,
                 priority, milestone_id, status, percent_complete),
            )
            conn.commit()
            task_id = cur.lastrowid
        assert task_id is not None
        task = self.get_task(task_id)
        assert task is not None  # just inserted
        return task

    def get_task(self, task_id: int) -> dict | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM task WHERE id=?", (task_id,)).fetchone()
        return dict(row) if row else None

    def update_task(self, task_id: int, **fields) -> dict:
        if fields:
            columns = ", ".join(f"{k}=?" for k in fields)
            with self._lock, self._connect() as conn:
                conn.execute(f"UPDATE task SET {columns} WHERE id=?", (*fields.values(), task_id))  # nosec B608 -- keys are hardcoded kwargs from call sites, not external input; values are bound
                conn.commit()
        task = self.get_task(task_id)
        assert task is not None  # caller passed an existing task_id
        return task

    def list_tasks(self, project: str) -> list[dict]:
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT * FROM task WHERE project=? ORDER BY id", (project,)).fetchall()
        return [dict(r) for r in rows]

    def add_dependency(self, predecessor_id: int, successor_id: int, type: str = "FS", lag_days: float = 0.0) -> dict:
        """Reject a dependency that would create a cycle in the task graph."""
        predecessor = self.get_task(predecessor_id)
        if predecessor is None:
            raise ValueError(f"no such task: {predecessor_id}")
        project = predecessor["project"]
        existing = self.list_dependencies(project)
        if _creates_cycle(existing, predecessor_id, successor_id):
            raise CyclicDependencyError(
                f"adding {predecessor_id}->{successor_id} would create a dependency cycle"
            )
        with self._lock, self._connect() as conn:
            conn.execute(
                """INSERT INTO dependency (predecessor_id, successor_id, type, lag_days) VALUES (?, ?, ?, ?)
                   ON CONFLICT(predecessor_id, successor_id) DO UPDATE SET type=excluded.type, lag_days=excluded.lag_days""",
                (predecessor_id, successor_id, type, lag_days),
            )
            conn.commit()
        return {"predecessor_id": predecessor_id, "successor_id": successor_id, "type": type, "lag_days": lag_days}

    def list_dependencies(self, project: str) -> list[dict]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """SELECT d.* FROM dependency d
                   JOIN task t ON t.id = d.predecessor_id
                   WHERE t.project=?""",
                (project,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Scenarios & scenario changes
    # ------------------------------------------------------------------

    def add_scenario(
        self, project: str, name: str, kind: str, *, parent_id: int | None = None, note: str | None = None,
    ) -> dict:
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO scenario (project, name, kind, parent_id, created, note) VALUES (?, ?, ?, ?, ?, ?)",
                (project, name, kind, parent_id, self._now(), note),
            )
            conn.commit()
            scenario_id = cur.lastrowid
        assert scenario_id is not None
        scenario = self.get_scenario(scenario_id)
        assert scenario is not None  # just inserted
        return scenario

    def get_scenario(self, scenario_id: int) -> dict | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM scenario WHERE id=?", (scenario_id,)).fetchone()
        return dict(row) if row else None

    def list_scenarios(self, project: str) -> list[dict]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM scenario WHERE project=? ORDER BY created DESC", (project,)
            ).fetchall()
        return [dict(r) for r in rows]

    def latest_scenario(self, project: str, *, kind: str | None = None) -> dict | None:
        scenarios = self.list_scenarios(project)
        if kind is not None:
            scenarios = [s for s in scenarios if s["kind"] == kind]
        return scenarios[0] if scenarios else None

    def add_scenario_change(self, scenario_id: int, entity: str, entity_id: int, field: str, value) -> dict:
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO scenario_change (scenario_id, entity, entity_id, field, value) VALUES (?, ?, ?, ?, ?)",
                (scenario_id, entity, entity_id, field, str(value) if value is not None else None),
            )
            conn.commit()
            change_id = cur.lastrowid
        return {"id": change_id, "scenario_id": scenario_id, "entity": entity, "entity_id": entity_id,
                "field": field, "value": value}

    def list_scenario_changes(self, scenario_id: int) -> list[dict]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM scenario_change WHERE scenario_id=?", (scenario_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    def commit_scenario(self, scenario_id: int, committed_by: str) -> dict:
        """Mark `scenario_id` committed and freeze a `baseline` clone of its
        allocation/schedule for future variance comparisons."""
        scenario = self.get_scenario(scenario_id)
        if scenario is None:
            raise ValueError(f"no such scenario: {scenario_id}")
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE scenario SET kind='committed', committed_by=? WHERE id=?",
                (committed_by, scenario_id),
            )
            cur = conn.execute(
                "INSERT INTO scenario (project, name, kind, parent_id, created, committed_by, note) "
                "VALUES (?, ?, 'baseline', ?, ?, ?, ?)",
                (scenario["project"], f"{scenario['name']} (baseline)", scenario_id, self._now(),
                 committed_by, "frozen at commit"),
            )
            baseline_id = cur.lastrowid
            conn.execute(
                "INSERT INTO allocation (scenario_id, task_id, resource_id, start_date, end_date, hours) "
                "SELECT ?, task_id, resource_id, start_date, end_date, hours FROM allocation WHERE scenario_id=?",
                (baseline_id, scenario_id),
            )
            conn.execute(
                "INSERT INTO schedule (scenario_id, task_id, earliest_start, earliest_finish, "
                "latest_start, latest_finish, slack_days, is_critical) "
                "SELECT ?, task_id, earliest_start, earliest_finish, latest_start, latest_finish, "
                "slack_days, is_critical FROM schedule WHERE scenario_id=?",
                (baseline_id, scenario_id),
            )
            conn.commit()
        return {"committed_scenario_id": scenario_id, "baseline_scenario_id": baseline_id}

    # ------------------------------------------------------------------
    # Allocation & schedule (per-scenario plan output)
    # ------------------------------------------------------------------

    def clear_allocation(self, scenario_id: int) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM allocation WHERE scenario_id=?", (scenario_id,))
            conn.commit()

    def add_allocation(
        self, scenario_id: int, task_id: int, resource_id: int, start_date: str, end_date: str, hours: float,
    ) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO allocation (scenario_id, task_id, resource_id, start_date, end_date, hours) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (scenario_id, task_id, resource_id, start_date, end_date, hours),
            )
            conn.commit()

    def list_allocations(self, scenario_id: int) -> list[dict]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM allocation WHERE scenario_id=? ORDER BY start_date", (scenario_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    def clear_schedule(self, scenario_id: int) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM schedule WHERE scenario_id=?", (scenario_id,))
            conn.commit()

    def set_schedule_row(
        self, scenario_id: int, task_id: int, *, earliest_start: str, earliest_finish: str,
        latest_start: str, latest_finish: str, slack_days: float, is_critical: bool,
    ) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO schedule (scenario_id, task_id, earliest_start, earliest_finish, "
                "latest_start, latest_finish, slack_days, is_critical) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(scenario_id, task_id) DO UPDATE SET "
                "earliest_start=excluded.earliest_start, earliest_finish=excluded.earliest_finish, "
                "latest_start=excluded.latest_start, latest_finish=excluded.latest_finish, "
                "slack_days=excluded.slack_days, is_critical=excluded.is_critical",
                (scenario_id, task_id, earliest_start, earliest_finish, latest_start, latest_finish,
                 slack_days, 1 if is_critical else 0),
            )
            conn.commit()

    def list_schedule(self, scenario_id: int) -> list[dict]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM schedule WHERE scenario_id=? ORDER BY task_id", (scenario_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Actuals
    # ------------------------------------------------------------------

    def add_actual(
        self, task_id: int, date: str, *, hours_logged: float | None = None,
        percent_complete: float | None = None, note: str | None = None,
    ) -> dict:
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO actual (task_id, date, hours_logged, percent_complete, note) VALUES (?, ?, ?, ?, ?)",
                (task_id, date, hours_logged, percent_complete, note),
            )
            conn.commit()
            actual_id = cur.lastrowid
        return {"id": actual_id, "task_id": task_id, "date": date, "hours_logged": hours_logged,
                "percent_complete": percent_complete, "note": note}

    def list_actuals(self, task_id: int) -> list[dict]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM actual WHERE task_id=? ORDER BY date", (task_id,)
            ).fetchall()
        return [dict(r) for r in rows]


def _creates_cycle(existing: list[dict], new_pred: int, new_succ: int) -> bool:
    """True if adding new_pred->new_succ would create a cycle, i.e. new_succ
    can already reach new_pred via existing edges."""
    if new_pred == new_succ:
        return True
    graph: dict[int, list[int]] = {}
    for d in existing:
        graph.setdefault(d["predecessor_id"], []).append(d["successor_id"])
    stack = [new_succ]
    seen: set[int] = set()
    while stack:
        node = stack.pop()
        if node == new_pred:
            return True
        if node in seen:
            continue
        seen.add(node)
        stack.extend(graph.get(node, []))
    return False
