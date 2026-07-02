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


def pm_allocate(acl: Acl, user_id: str, project: str, scenario_id: int, project_start: str | None = None, *, _pm) -> dict:
    acl.enforce(user_id, project, "owner")
    _owned_scenario(_pm, project, scenario_id)
    from datetime import date as _date

    start = _date.fromisoformat(project_start) if project_start else None
    return _run_allocate(_pm, scenario_id, project_start=start)


def pm_utilization(
    acl: Acl, user_id: str, project: str, scenario_id: int, period_start: str, period_end: str,
    resource_id: int | None = None, *, _pm,
) -> dict:
    acl.enforce(user_id, project, "reader")
    _owned_scenario(_pm, project, scenario_id)
    return _run_utilization(_pm, scenario_id, period_start, period_end, resource_id=resource_id)


def pm_variance(acl: Acl, user_id: str, project: str, *, _pm) -> dict:
    acl.enforce(user_id, project, "reader")
    return _run_variance(_pm, project)


def plan_commit(acl: Acl, user_id: str, project: str, scenario_id: int, *, _pm) -> dict:
    acl.enforce(user_id, project, "owner")
    _owned_scenario(_pm, project, scenario_id)
    return _pm.commit_scenario(scenario_id, user_id)
