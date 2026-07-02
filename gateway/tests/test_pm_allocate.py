# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for pm.allocate.allocate and pm.report.{utilization,variance}
(FEATURE-PM-ENGINE.md §4)."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from memaix_gateway.pm.allocate import allocate
from memaix_gateway.pm.report import utilization, variance
from memaix_gateway.pm.store import PMStore

START = date(2025, 1, 6)


@pytest.fixture()
def store(tmp_path):
    return PMStore.for_path(tmp_path / "pm.db")


def test_allocate_assigns_single_task_to_only_resource(store):
    scenario = store.add_scenario("acme", "Plan", "baseline")
    r = store.add_resource("acme", "Anna", capacity_hours_per_day=8.0)
    t = store.add_task("acme", "Design", estimate_hours=16)

    result = allocate(store, scenario["id"], project_start=START)

    assert result["warnings"] == []
    allocs = store.list_allocations(scenario["id"])
    assert len(allocs) == 1
    assert allocs[0]["resource_id"] == r["id"]
    assert allocs[0]["task_id"] == t["id"]
    assert allocs[0]["start_date"] == "2025-01-06"
    assert allocs[0]["end_date"] == "2025-01-07"  # 16h at 8h/day = 2 days


def test_allocate_respects_required_skill(store):
    scenario = store.add_scenario("acme", "Plan", "baseline")
    python_skill = store.get_or_create_skill("acme", "python")
    anna = store.add_resource("acme", "Anna")
    erik = store.add_resource("acme", "Erik")
    store.set_resource_skill(anna["id"], python_skill["id"])
    t = store.add_task("acme", "Backend work", estimate_hours=8, required_skill_id=python_skill["id"])

    allocate(store, scenario["id"], project_start=START)

    allocs = store.list_allocations(scenario["id"])
    assert allocs[0]["resource_id"] == anna["id"]
    assert erik["id"] not in [a["resource_id"] for a in allocs]


def test_allocate_warns_when_no_resource_has_required_skill(store):
    scenario = store.add_scenario("acme", "Plan", "baseline")
    rare_skill = store.get_or_create_skill("acme", "cobol")
    store.add_resource("acme", "Anna")
    store.add_task("acme", "Legacy migration", estimate_hours=8, required_skill_id=rare_skill["id"])

    result = allocate(store, scenario["id"], project_start=START)

    assert store.list_allocations(scenario["id"]) == []
    assert any("no eligible resource" in w for w in result["warnings"])


def test_allocate_warns_on_missing_estimate(store):
    scenario = store.add_scenario("acme", "Plan", "baseline")
    store.add_resource("acme", "Anna")
    store.add_task("acme", "Unclear scope")  # no estimate_hours

    result = allocate(store, scenario["id"], project_start=START)

    assert store.list_allocations(scenario["id"]) == []
    assert any("no estimate" in w for w in result["warnings"])


def test_allocate_does_not_overbook_a_resource(store):
    scenario = store.add_scenario("acme", "Plan", "baseline")
    store.add_resource("acme", "Anna", capacity_hours_per_day=8.0)
    t1 = store.add_task("acme", "Task 1", estimate_hours=8, priority=1)
    t2 = store.add_task("acme", "Task 2", estimate_hours=8, priority=1)

    allocate(store, scenario["id"], project_start=START)

    allocs = {a["task_id"]: a for a in store.list_allocations(scenario["id"])}
    # Same resource, same 8h/day capacity, two independent 8h tasks -> must land on different days.
    assert allocs[t1["id"]]["start_date"] != allocs[t2["id"]]["start_date"]


def test_allocate_places_second_task_after_first_when_only_one_resource(store):
    scenario = store.add_scenario("acme", "Plan", "baseline")
    store.add_resource("acme", "Anna", capacity_hours_per_day=8.0)
    t1 = store.add_task("acme", "Task 1", estimate_hours=8, priority=1)
    t2 = store.add_task("acme", "Task 2", estimate_hours=8, priority=2)

    allocate(store, scenario["id"], project_start=START)
    allocs = {a["task_id"]: a for a in store.list_allocations(scenario["id"])}
    assert allocs[t1["id"]]["start_date"] == "2025-01-06"
    assert allocs[t2["id"]]["start_date"] == "2025-01-07"


def test_allocate_respects_dependency_order(store):
    scenario = store.add_scenario("acme", "Plan", "baseline")
    store.add_resource("acme", "Anna", capacity_hours_per_day=8.0)
    t1 = store.add_task("acme", "Design", estimate_hours=8)
    t2 = store.add_task("acme", "Build", estimate_hours=8)
    store.add_dependency(t1["id"], t2["id"])

    allocate(store, scenario["id"], project_start=START)
    allocs = {a["task_id"]: a for a in store.list_allocations(scenario["id"])}
    assert allocs[t2["id"]]["start_date"] > allocs[t1["id"]]["start_date"]


def test_allocate_respects_availability_exception(store):
    scenario = store.add_scenario("acme", "Plan", "baseline")
    r = store.add_resource("acme", "Anna", capacity_hours_per_day=8.0)
    store.add_availability(r["id"], "2025-01-06", "2025-01-06", 0.0, reason="holiday")
    store.add_task("acme", "Task", estimate_hours=4)

    allocate(store, scenario["id"], project_start=START)
    allocs = store.list_allocations(scenario["id"])
    assert allocs[0]["start_date"] == "2025-01-07"  # skipped the 0-capacity day


def test_allocate_is_idempotent_replacing_prior_run(store):
    scenario = store.add_scenario("acme", "Plan", "baseline")
    store.add_resource("acme", "Anna", capacity_hours_per_day=8.0)
    store.add_task("acme", "Task", estimate_hours=8)

    allocate(store, scenario["id"], project_start=START)
    allocate(store, scenario["id"], project_start=START)

    assert len(store.list_allocations(scenario["id"])) == 1


def test_allocate_writes_critical_path_schedule(store):
    scenario = store.add_scenario("acme", "Plan", "baseline")
    store.add_resource("acme", "Anna")
    t = store.add_task("acme", "Task", estimate_hours=8)

    allocate(store, scenario["id"], project_start=START)

    sched = store.list_schedule(scenario["id"])
    assert len(sched) == 1
    assert sched[0]["task_id"] == t["id"]
    assert sched[0]["is_critical"] == 1


def test_allocate_unknown_scenario_raises(store):
    with pytest.raises(ValueError):
        allocate(store, 999)


# ------------------------------------------------------------------
# utilization
# ------------------------------------------------------------------


def test_utilization_full_capacity_used(store):
    scenario = store.add_scenario("acme", "Plan", "baseline")
    store.add_resource("acme", "Anna", capacity_hours_per_day=8.0)
    store.add_task("acme", "Task", estimate_hours=16)
    allocate(store, scenario["id"], project_start=START)

    report = utilization(store, scenario["id"], "2025-01-06", "2025-01-07")
    assert report["resources"][0]["allocated_hours"] == 16.0
    assert report["resources"][0]["capacity_hours"] == 16.0
    assert report["resources"][0]["utilization_pct"] == 100.0


def test_utilization_zero_when_unallocated(store):
    scenario = store.add_scenario("acme", "Plan", "baseline")
    store.add_resource("acme", "Anna", capacity_hours_per_day=8.0)
    report = utilization(store, scenario["id"], "2025-01-06", "2025-01-10")
    assert report["resources"][0]["allocated_hours"] == 0.0
    assert report["resources"][0]["utilization_pct"] == 0.0


def test_utilization_unknown_scenario_raises(store):
    with pytest.raises(ValueError):
        utilization(store, 999, "2025-01-06", "2025-01-10")


# ------------------------------------------------------------------
# variance
# ------------------------------------------------------------------


def test_variance_without_baseline_returns_error(store):
    store.add_task("acme", "Task", estimate_hours=8)
    result = variance(store, "acme")
    assert result["ok"] is False


def test_variance_flags_slippage_when_incomplete_past_planned_finish(store):
    scenario = store.add_scenario("acme", "Plan", "baseline")
    store.add_resource("acme", "Anna")
    t = store.add_task("acme", "Task", estimate_hours=8)
    allocate(store, scenario["id"], project_start=START)
    store.commit_scenario(scenario["id"], "alice")

    result = variance(store, "acme", today=date(2025, 1, 20))
    row = result["tasks"][0]
    assert row["task_id"] == t["id"]
    assert row["slippage_days"] is not None
    assert row["slippage_days"] > 0


def test_variance_no_slippage_when_done_on_time(store):
    scenario = store.add_scenario("acme", "Plan", "baseline")
    store.add_resource("acme", "Anna")
    t = store.add_task("acme", "Task", estimate_hours=8)
    allocate(store, scenario["id"], project_start=START)
    store.commit_scenario(scenario["id"], "alice")
    store.add_actual(t["id"], "2025-01-06", hours_logged=8.0, percent_complete=100.0)

    result = variance(store, "acme", today=date(2025, 1, 20))
    row = result["tasks"][0]
    assert row["slippage_days"] is None
    assert row["percent_complete"] == 100.0


def test_variance_hours_variance_computed(store):
    scenario = store.add_scenario("acme", "Plan", "baseline")
    store.add_resource("acme", "Anna")
    t = store.add_task("acme", "Task", estimate_hours=8)
    allocate(store, scenario["id"], project_start=START)
    store.commit_scenario(scenario["id"], "alice")
    store.add_actual(t["id"], "2025-01-06", hours_logged=12.0, percent_complete=100.0)

    result = variance(store, "acme", today=date(2025, 1, 20))
    assert result["tasks"][0]["hours_variance"] == 4.0


def test_allocate_defaults_project_start_to_utc_today_not_server_local(store):
    # OPEN-GAPS.md #16 — must never fall back to server-local date.today().
    scenario = store.add_scenario("acme", "Plan", "baseline")
    store.add_resource("acme", "Anna")
    store.add_task("acme", "Task", estimate_hours=8)

    result = allocate(store, scenario["id"])  # no project_start override

    utc_today = datetime.now(timezone.utc).date().isoformat()
    assert result["schedule"][0]["earliest_start"] == utc_today


def test_variance_defaults_today_to_utc_not_server_local(store):
    scenario = store.add_scenario("acme", "Plan", "baseline")
    store.add_resource("acme", "Anna")
    t = store.add_task("acme", "Task", estimate_hours=8)
    allocate(store, scenario["id"], project_start=START)
    store.commit_scenario(scenario["id"], "alice")
    store.add_actual(t["id"], "2025-01-06", hours_logged=8.0, percent_complete=50.0)

    result = variance(store, "acme")  # no today override

    utc_today = datetime.now(timezone.utc).date()
    planned_finish = date.fromisoformat(result["tasks"][0]["planned_finish"])
    expected_slippage = (utc_today - planned_finish).days
    assert result["tasks"][0]["slippage_days"] == expected_slippage
