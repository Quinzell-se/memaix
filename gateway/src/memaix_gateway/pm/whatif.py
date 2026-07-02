# SPDX-License-Identifier: AGPL-3.0-or-later
"""What-if scenarios — consequence analysis without touching the committed
plan (FEATURE-PM-ENGINE.md §4, PM-PLANNING-ENGINE.md "Konsekvensanalys").

whatif() clones the base scenario as a new kind='whatif' scenario, applies
the requested changes as scenario_change rows (the same overlay allocate.py
already reads — see allocate._apply_overlay), runs allocate() against the
clone, and diffs its resulting schedule/allocation against the base
scenario's *already-stored* schedule/allocation. It never recomputes or
mutates the base — only the new clone is written to.

If the base scenario hasn't been allocate()'d yet, its schedule/allocation
are simply empty and every whatif task will show up as a "change" (nothing
to compare against). Run allocate() on the base first for a meaningful diff.
"""

from __future__ import annotations

from datetime import date

from .allocate import allocate


def whatif(
    store, base_scenario_id: int, changes: list[dict], *, project_start: date | None = None, allocator=None,
) -> dict:
    """Simulate `changes` (scenario_change-shaped dicts: entity/entity_id/
    field/value) against `base_scenario_id` without touching it. Returns a
    diff: {whatif_scenario_id, base_scenario_id, warnings, schedule_changes,
    resource_changes, milestone_changes}.

    `allocator` defaults to the heuristic (pm/allocate.py); pass
    pm/allocate_cpsat.py's allocate_cpsat to run what-if through CP-SAT
    instead (tools/pm_engine.py selects it from config)."""
    run_allocate = allocator or allocate
    base = store.get_scenario(base_scenario_id)
    if base is None:
        raise ValueError(f"no such scenario: {base_scenario_id}")
    project = base["project"]

    whatif_scenario = store.add_scenario(
        project, f"whatif of {base['name']}", "whatif", parent_id=base_scenario_id,
    )
    for change in changes:
        store.add_scenario_change(
            whatif_scenario["id"], change["entity"], change["entity_id"], change["field"], change["value"],
        )

    result = run_allocate(store, whatif_scenario["id"], project_start=project_start)

    tasks_by_id = {t["id"]: t for t in store.list_tasks(project)}
    base_schedule = {r["task_id"]: r for r in store.list_schedule(base_scenario_id)}
    whatif_schedule = {r["task_id"]: r for r in store.list_schedule(whatif_scenario["id"])}
    base_alloc = {a["task_id"]: a for a in store.list_allocations(base_scenario_id)}
    whatif_alloc = {a["task_id"]: a for a in store.list_allocations(whatif_scenario["id"])}

    schedule_changes = []
    for task_id in sorted(set(base_schedule) & set(whatif_schedule)):
        b, w = base_schedule[task_id], whatif_schedule[task_id]
        if b["earliest_finish"] != w["earliest_finish"] or bool(b["is_critical"]) != bool(w["is_critical"]):
            schedule_changes.append(
                {
                    "task_id": task_id,
                    "title": tasks_by_id.get(task_id, {}).get("title", ""),
                    "base_finish": b["earliest_finish"], "whatif_finish": w["earliest_finish"],
                    "base_is_critical": bool(b["is_critical"]), "whatif_is_critical": bool(w["is_critical"]),
                }
            )

    resource_changes = []
    for task_id in sorted(set(base_alloc) | set(whatif_alloc)):
        b_res = base_alloc.get(task_id, {}).get("resource_id")
        w_res = whatif_alloc.get(task_id, {}).get("resource_id")
        if b_res != w_res:
            resource_changes.append(
                {"task_id": task_id, "title": tasks_by_id.get(task_id, {}).get("title", ""),
                 "base_resource_id": b_res, "whatif_resource_id": w_res}
            )

    milestone_changes = []
    for milestone in store.list_milestones(project):
        m_tasks = [t for t in tasks_by_id.values() if t.get("milestone_id") == milestone["id"]]
        base_finish = max(
            (base_schedule[t["id"]]["earliest_finish"] for t in m_tasks if t["id"] in base_schedule), default=None,
        )
        whatif_finish = max(
            (whatif_schedule[t["id"]]["earliest_finish"] for t in m_tasks if t["id"] in whatif_schedule), default=None,
        )
        if base_finish != whatif_finish:
            milestone_changes.append(
                {
                    "milestone_id": milestone["id"], "name": milestone["name"], "target_date": milestone["target_date"],
                    "base_finish": base_finish, "whatif_finish": whatif_finish,
                }
            )

    return {
        "whatif_scenario_id": whatif_scenario["id"],
        "base_scenario_id": base_scenario_id,
        "warnings": result["warnings"],
        "schedule_changes": schedule_changes,
        "resource_changes": resource_changes,
        "milestone_changes": milestone_changes,
    }
