# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for pm.allocate_cpsat — the optional OR-Tools CP-SAT allocator
(FEATURE-PM-ENGINE.md Byggordning steg 7). Same constraints as the
heuristic (capacity/skill/dependencies), solved via optimization instead
of greedy placement. Skipped entirely if ortools isn't installed."""

from __future__ import annotations

import sys
from datetime import date

import pytest

pytest.importorskip("ortools")

from memaix_gateway.pm.allocate_cpsat import allocate_cpsat
from memaix_gateway.pm.store import PMStore

START = date(2025, 1, 6)  # a Monday, matching test_pm_allocate.py's convention


@pytest.fixture()
def store(tmp_path):
    return PMStore.for_path(tmp_path / "pm.db")


def test_single_task_single_resource(store):
    scenario = store.add_scenario("acme", "Plan", "baseline")
    r = store.add_resource("acme", "Anna", capacity_hours_per_day=8.0)
    t = store.add_task("acme", "Design", estimate_hours=16)

    result = allocate_cpsat(store, scenario["id"], project_start=START)

    assert result["warnings"] == []
    allocs = store.list_allocations(scenario["id"])
    assert len(allocs) == 1
    assert allocs[0]["resource_id"] == r["id"]
    assert allocs[0]["task_id"] == t["id"]
    assert allocs[0]["start_date"] == "2025-01-06"
    assert allocs[0]["end_date"] == "2025-01-07"  # 16h at 8h/day = 2 days


def test_two_tasks_same_resource_do_not_overlap(store):
    scenario = store.add_scenario("acme", "Plan", "baseline")
    store.add_resource("acme", "Anna", capacity_hours_per_day=8.0)
    store.add_task("acme", "A", estimate_hours=8)
    store.add_task("acme", "B", estimate_hours=8)

    result = allocate_cpsat(store, scenario["id"], project_start=START)

    allocs = sorted(result["allocations"], key=lambda a: a["start_date"])
    a_start, a_end = date.fromisoformat(allocs[0]["start_date"]), date.fromisoformat(allocs[0]["end_date"])
    b_start = date.fromisoformat(allocs[1]["start_date"])
    assert b_start > a_end  # no overlap on the shared resource


def test_independent_tasks_on_separate_resources_run_in_parallel(store):
    # Proves the objective actually minimizes makespan rather than always
    # serializing: two tasks with no dependency and no resource contention
    # must both start on day 0, not one after the other.
    scenario = store.add_scenario("acme", "Plan", "baseline")
    store.add_resource("acme", "Anna", capacity_hours_per_day=8.0)
    store.add_resource("acme", "Bob", capacity_hours_per_day=8.0)
    store.add_task("acme", "A", estimate_hours=8)
    store.add_task("acme", "B", estimate_hours=8)

    result = allocate_cpsat(store, scenario["id"], project_start=START)

    starts = {a["start_date"] for a in result["allocations"]}
    assert starts == {"2025-01-06"}


def test_dependency_respected(store):
    scenario = store.add_scenario("acme", "Plan", "baseline")
    store.add_resource("acme", "Anna", capacity_hours_per_day=8.0)
    a = store.add_task("acme", "A", estimate_hours=8)
    b = store.add_task("acme", "B", estimate_hours=8)
    store.add_dependency(a["id"], b["id"], type="FS")

    result = allocate_cpsat(store, scenario["id"], project_start=START)

    by_task = {alloc["task_id"]: alloc for alloc in result["allocations"]}
    assert date.fromisoformat(by_task[b["id"]]["start_date"]) > date.fromisoformat(by_task[a["id"]]["end_date"])


def test_required_skill_respected(store):
    scenario = store.add_scenario("acme", "Plan", "baseline")
    python_skill = store.get_or_create_skill("acme", "python")
    anna = store.add_resource("acme", "Anna")
    bob = store.add_resource("acme", "Bob")
    store.set_resource_skill(anna["id"], python_skill["id"])
    t = store.add_task("acme", "Backend work", estimate_hours=8, required_skill_id=python_skill["id"])

    result = allocate_cpsat(store, scenario["id"], project_start=START)

    assert result["allocations"][0]["resource_id"] == anna["id"]
    assert result["allocations"][0]["resource_id"] != bob["id"]


def test_no_estimate_is_zero_duration_with_warning(store):
    scenario = store.add_scenario("acme", "Plan", "baseline")
    store.add_resource("acme", "Anna")
    t = store.add_task("acme", "Vague task")

    result = allocate_cpsat(store, scenario["id"], project_start=START)

    assert result["allocations"] == []
    assert any(str(t["id"]) in w and "no estimate" in w for w in result["warnings"])


def test_no_eligible_resource_is_unallocated_with_warning(store):
    scenario = store.add_scenario("acme", "Plan", "baseline")
    skill = store.get_or_create_skill("acme", "rust")
    t = store.add_task("acme", "Needs rust", estimate_hours=8, required_skill_id=skill["id"])

    result = allocate_cpsat(store, scenario["id"], project_start=START)

    assert result["allocations"] == []
    assert any(str(t["id"]) in w and "no eligible resource" in w for w in result["warnings"])


def test_schedule_matches_cpm_regardless_of_allocation(store):
    from memaix_gateway.pm.allocate import allocate as allocate_heuristic

    scenario = store.add_scenario("acme", "Plan", "baseline")
    scenario2 = store.add_scenario("acme", "Plan2", "baseline")
    store.add_resource("acme", "Anna", capacity_hours_per_day=8.0)
    store.add_task("acme", "A", estimate_hours=16)

    heuristic_result = allocate_heuristic(store, scenario["id"], project_start=START)
    cpsat_result = allocate_cpsat(store, scenario2["id"], project_start=START)

    assert cpsat_result["schedule"] == heuristic_result["schedule"]


def test_no_schedulable_tasks_returns_empty_cleanly(store):
    scenario = store.add_scenario("acme", "Plan", "baseline")
    store.add_task("acme", "Unestimated")

    result = allocate_cpsat(store, scenario["id"], project_start=START)

    assert result["allocations"] == []
    assert len(result["schedule"]) == 1


def test_unknown_scenario_raises(store):
    with pytest.raises(ValueError):
        allocate_cpsat(store, 999)


def test_missing_ortools_raises_clear_import_error(store, monkeypatch):
    scenario = store.add_scenario("acme", "Plan", "baseline")
    monkeypatch.setitem(sys.modules, "ortools.sat.python", None)

    with pytest.raises(ImportError, match="ortools"):
        allocate_cpsat(store, scenario["id"], project_start=START)
