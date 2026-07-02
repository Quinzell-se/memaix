# SPDX-License-Identifier: AGPL-3.0-or-later
"""PM planning-engine tools — resources/tasks/scenarios/allocate/utilization/
variance/plan_commit (FEATURE-PM-ENGINE.md §5).

Distinct from tools/pm.py (methodology/sprints/RAID/status — markdown+git,
backlog-flavored PM). This module is the deterministic planning engine:
SQLite-backed, numeric ids, critical path + resource-constrained allocation.
`_pm` is a pm.store.PMStore, injected the same way `_dav`/`_imap` are.

RBAC per PM-AGENT.md: reading is 'reader', authoring tasks/resources is
'collaborator', anything that changes the committed plan (`allocate`,
`plan_commit`, availability/resource setup) is 'owner'.
"""

from __future__ import annotations

from ..acl import Acl
from ..pm.allocate import allocate as _run_allocate
from ..pm.report import utilization as _run_utilization
from ..pm.report import variance as _run_variance
from ..pm.whatif import whatif as _run_whatif


def _resolve_allocator(cfg: dict):
    """`memaix.yaml`'s `pm.allocator: heuristic|cpsat` (default heuristic)
    selects pm/allocate.py's greedy heuristic or pm/allocate_cpsat.py's
    CP-SAT optimizer (FEATURE-PM-ENGINE.md Byggordning steg 7/8). The
    ortools import only happens when cpsat is actually requested, so a
    default (heuristic) install never needs the optional dependency."""
    allocator_name = cfg.get("memaix", {}).get("pm", {}).get("allocator", "heuristic")
    if allocator_name == "cpsat":
        from ..pm.allocate_cpsat import allocate_cpsat

        return allocate_cpsat
    if allocator_name != "heuristic":
        raise ValueError(f"unknown pm.allocator: {allocator_name!r}; valid: 'heuristic', 'cpsat'")
    return _run_allocate


def _owned_task(pm, project: str, task_id: int) -> dict:
    task = pm.get_task(task_id)
    if task is None or task["project"] != project:
        raise FileNotFoundError(f"no such task in project {project!r}: {task_id}")
    return task


def _owned_resource(pm, project: str, resource_id: int) -> dict:
    resource = pm.get_resource(resource_id)
    if resource is None or resource["project"] != project:
        raise FileNotFoundError(f"no such resource in project {project!r}: {resource_id}")
    return resource


def _owned_milestone(pm, project: str, milestone_id: int) -> None:
    if milestone_id not in {m["id"] for m in pm.list_milestones(project)}:
        raise FileNotFoundError(f"no such milestone in project {project!r}: {milestone_id}")


def _owned_scenario(pm, project: str, scenario_id: int) -> dict:
    scenario = pm.get_scenario(scenario_id)
    if scenario is None or scenario["project"] != project:
        raise FileNotFoundError(f"no such scenario in project {project!r}: {scenario_id}")
    return scenario


def resource_add(
    acl: Acl, user_id: str, project: str, name: str, *,
    cost_per_hour: float | None = None, capacity_hours_per_day: float = 8.0, _pm,
) -> dict:
    acl.enforce(user_id, project, "owner")
    return _pm.add_resource(project, name, cost_per_hour=cost_per_hour, capacity_hours_per_day=capacity_hours_per_day)


def resource_list(acl: Acl, user_id: str, project: str, *, _pm) -> list[dict]:
    acl.enforce(user_id, project, "reader")
    return _pm.list_resources(project)


def resource_availability(
    acl: Acl, user_id: str, project: str, resource_id: int, start_date: str, end_date: str,
    hours_per_day: float, reason: str | None = None, *, _pm,
) -> dict:
    acl.enforce(user_id, project, "owner")
    _owned_resource(_pm, project, resource_id)
    return _pm.add_availability(resource_id, start_date, end_date, hours_per_day, reason)


def resource_set_skill(
    acl: Acl, user_id: str, project: str, resource_id: int, skill: str, level: int | None = None, *, _pm,
) -> dict:
    acl.enforce(user_id, project, "owner")
    _owned_resource(_pm, project, resource_id)
    skill_row = _pm.get_or_create_skill(project, skill)
    _pm.set_resource_skill(resource_id, skill_row["id"], level)
    return {"resource_id": resource_id, "skill": skill, "skill_id": skill_row["id"], "level": level}


def milestone_add(acl: Acl, user_id: str, project: str, name: str, target_date: str | None = None, *, _pm) -> dict:
    acl.enforce(user_id, project, "owner")
    return _pm.add_milestone(project, name, target_date)


def task_add(
    acl: Acl, user_id: str, project: str, title: str, *,
    estimate_hours: float | None = None, required_skill: str | None = None, priority: int = 3,
    backlog_id: str | None = None, milestone_id: int | None = None, _pm,
) -> dict:
    acl.enforce(user_id, project, "collaborator")
    if milestone_id is not None:
        _owned_milestone(_pm, project, milestone_id)  # reject a milestone id from another project
    skill_id = _pm.get_or_create_skill(project, required_skill)["id"] if required_skill else None
    return _pm.add_task(
        project, title, backlog_id=backlog_id, estimate_hours=estimate_hours,
        required_skill_id=skill_id, priority=priority, milestone_id=milestone_id,
    )


def task_estimate(acl: Acl, user_id: str, project: str, task_id: int, estimate_hours: float, *, _pm) -> dict:
    acl.enforce(user_id, project, "collaborator")
    _owned_task(_pm, project, task_id)
    return _pm.update_task(task_id, estimate_hours=estimate_hours)


def task_log_actual(
    acl: Acl, user_id: str, project: str, task_id: int, date: str, *,
    hours_logged: float | None = None, percent_complete: float | None = None, note: str | None = None, _pm,
) -> dict:
    acl.enforce(user_id, project, "collaborator")
    _owned_task(_pm, project, task_id)
    if percent_complete is not None:
        _pm.update_task(task_id, percent_complete=percent_complete)
    return _pm.add_actual(task_id, date, hours_logged=hours_logged, percent_complete=percent_complete, note=note)


def dependency_add(
    acl: Acl, user_id: str, project: str, predecessor_id: int, successor_id: int,
    type: str = "FS", lag_days: float = 0.0, *, _pm,
) -> dict:
    acl.enforce(user_id, project, "collaborator")
    _owned_task(_pm, project, predecessor_id)
    _owned_task(_pm, project, successor_id)
    return _pm.add_dependency(predecessor_id, successor_id, type, lag_days)


def scenario_add(acl: Acl, user_id: str, project: str, name: str, *, _pm) -> dict:
    acl.enforce(user_id, project, "collaborator")
    return _pm.add_scenario(project, name, kind="baseline")


def scenario_list(acl: Acl, user_id: str, project: str, *, _pm) -> list[dict]:
    acl.enforce(user_id, project, "reader")
    return _pm.list_scenarios(project)


def pm_allocate(
    acl: Acl, user_id: str, project: str, scenario_id: int, project_start: str | None = None, *, _pm, _cfg=None,
) -> dict:
    acl.enforce(user_id, project, "owner")
    _owned_scenario(_pm, project, scenario_id)
    from datetime import date as _date

    from .. import config

    cfg = _cfg if _cfg is not None else config.load()
    allocator = _resolve_allocator(cfg)
    start = _date.fromisoformat(project_start) if project_start else None
    return allocator(_pm, scenario_id, project_start=start)


_WHATIF_CHANGE_FIELDS = {
    "task": {"estimate_hours", "priority", "required_skill_id"},
    "resource": {"active"},
}


def pm_whatif(
    acl: Acl, user_id: str, project: str, base_scenario_id: int, changes: list[dict],
    project_start: str | None = None, *, _pm, _cfg=None,
) -> dict:
    """Simulate `changes` against `base_scenario_id` in a fresh scenario,
    without touching the base. Each change is {entity: 'task'|'resource',
    entity_id, field, value} — see allocate.py's supported overlay fields."""
    acl.enforce(user_id, project, "collaborator")
    _owned_scenario(_pm, project, base_scenario_id)
    for change in changes:
        entity, entity_id, field = change.get("entity"), change.get("entity_id"), change.get("field")
        if not isinstance(entity_id, int):
            raise ValueError(f"whatif change entity_id must be an int, got {entity_id!r}")
        if entity == "task":
            _owned_task(_pm, project, entity_id)
        elif entity == "resource":
            _owned_resource(_pm, project, entity_id)
        else:
            raise ValueError(f"unsupported whatif entity: {entity!r} (must be 'task' or 'resource')")
        if field not in _WHATIF_CHANGE_FIELDS[entity]:
            raise ValueError(f"unsupported whatif field for {entity!r}: {field!r}")

    from datetime import date as _date

    from .. import config

    cfg = _cfg if _cfg is not None else config.load()
    allocator = _resolve_allocator(cfg)
    start = _date.fromisoformat(project_start) if project_start else None
    return _run_whatif(_pm, base_scenario_id, changes, project_start=start, allocator=allocator)


def pm_utilization(
    acl: Acl, user_id: str, project: str, scenario_id: int, period_start: str, period_end: str,
    resource_id: int | None = None, *, _pm,
) -> dict:
    acl.enforce(user_id, project, "reader")
    _owned_scenario(_pm, project, scenario_id)
    return _run_utilization(_pm, scenario_id, period_start, period_end, resource_id=resource_id)


def pm_variance(acl: Acl, user_id: str, project: str, today: str | None = None, *, _pm) -> dict:
    acl.enforce(user_id, project, "reader")
    from datetime import date as _date

    as_of = _date.fromisoformat(today) if today else None
    return _run_variance(_pm, project, today=as_of)


def plan_commit(acl: Acl, user_id: str, project: str, scenario_id: int, *, _pm) -> dict:
    acl.enforce(user_id, project, "owner")
    _owned_scenario(_pm, project, scenario_id)
    return _pm.commit_scenario(scenario_id, user_id)


_REPORT_KINDS = {"status", "milestones", "variance", "raid", "utilization"}
_AUDIENCES = {"team", "leadership"}


def _milestone_rollup(milestones: list[dict], today, audience: str) -> list[dict]:
    from datetime import date as _date

    rows = []
    for m in milestones:
        target = _date.fromisoformat(m["target_date"]) if m.get("target_date") else None
        rows.append({
            "id": m["id"], "name": m["name"], "target_date": m.get("target_date"),
            "status": m["status"], "overdue": bool(target and target < today),
        })
    if audience == "leadership":
        # Condensed view: only what leadership needs to act on. There's no
        # milestone_set_status tool yet, so `status` is always "open" today
        # — filtering by overdue-ness is the only real signal available.
        rows = [r for r in rows if r["overdue"]]
    return rows


def _raid_rollup(raid: dict, audience: str) -> dict:
    entries = raid.get("entries", [])
    if audience == "leadership":
        # Same caveat as milestones: pm_raid_add always writes status='open'
        # (no close tool yet) — the status filter is forward-looking, the
        # severity filter is what actually condenses today.
        entries = [
            e for e in entries
            if e.get("status", "open") == "open" and e.get("severity", "").lower() in ("high", "critical")
        ]
    return {"entries": entries, "count": len(entries)}


def pm_report(
    acl: Acl, user_id: str, project: str, kind: str = "status", audience: str = "team",
    scenario_id: int | None = None, period_start: str | None = None, period_end: str | None = None,
    *, _pm,
) -> dict:
    """Rollup PM data for the LLM to narrate (FEATURE-PM-ENGINE.md §5) — never
    computes anything new, just re-packages/filters what allocate/variance/
    the RAID log already produced. `kind` selects which sections to include
    ('status' = everything except utilization, which needs scenario_id +
    a period and so isn't part of the default bundle); `audience` levels
    the detail ('leadership' condenses to overdue milestones + high/critical
    RAID entries, dropping per-task noise 'team' gets)."""
    acl.enforce(user_id, project, "reader")
    if kind not in _REPORT_KINDS:
        raise ValueError(f"unknown report kind: {kind!r}; valid: {sorted(_REPORT_KINDS)}")
    if audience not in _AUDIENCES:
        raise ValueError(f"unknown audience: {audience!r}; valid: {sorted(_AUDIENCES)}")

    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).date()
    report: dict = {"project": project, "kind": kind, "audience": audience}

    if kind in ("status", "milestones"):
        report["milestones"] = _milestone_rollup(_pm.list_milestones(project), today, audience)

    if kind in ("status", "variance"):
        report["variance"] = _run_variance(_pm, project, today=today)

    if kind in ("status", "raid"):
        from . import pm as t_pm

        try:
            raid = t_pm.pm_raid_list(acl, user_id, project)
        except ValueError:
            raid = {"ok": True, "entries": [], "count": 0, "note": "no vault configured"}
        report["raid"] = _raid_rollup(raid, audience)

    if kind == "utilization":
        if scenario_id is None or not period_start or not period_end:
            raise ValueError("utilization report requires scenario_id, period_start and period_end")
        _owned_scenario(_pm, project, scenario_id)
        report["utilization"] = _run_utilization(_pm, scenario_id, period_start, period_end)

    return report
