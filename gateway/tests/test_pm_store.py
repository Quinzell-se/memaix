# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for pm.store.PMStore — schema CRUD + the DAG invariant on dependency."""

from __future__ import annotations

import pytest

from memaix_gateway.pm.store import CyclicDependencyError, PMStore


@pytest.fixture()
def store(tmp_path):
    return PMStore.for_path(tmp_path / "pm.db")


def test_add_and_list_resources_are_project_scoped(store):
    store.add_resource("acme", "Anna")
    store.add_resource("acme", "Erik")
    store.add_resource("other", "Bob")
    assert {r["name"] for r in store.list_resources("acme")} == {"Anna", "Erik"}
    assert {r["name"] for r in store.list_resources("other")} == {"Bob"}


def test_resource_defaults(store):
    r = store.add_resource("acme", "Anna")
    assert r["capacity_hours_per_day"] == 8.0
    assert r["active"] is True
    assert r["cost_per_hour"] is None


def test_list_resources_active_only(store):
    store.add_resource("acme", "Anna", active=True)
    store.add_resource("acme", "Erik", active=False)
    assert len(store.list_resources("acme")) == 2
    assert len(store.list_resources("acme", active_only=True)) == 1


def test_get_or_create_skill_is_idempotent(store):
    a = store.get_or_create_skill("acme", "python")
    b = store.get_or_create_skill("acme", "python")
    assert a["id"] == b["id"]


def test_resource_skill_roundtrip(store):
    r = store.add_resource("acme", "Anna")
    skill = store.get_or_create_skill("acme", "python")
    store.set_resource_skill(r["id"], skill["id"], level=4)
    assert store.list_resource_skill_ids(r["id"]) == {skill["id"]}


def test_availability_roundtrip(store):
    r = store.add_resource("acme", "Anna")
    store.add_availability(r["id"], "2025-01-06", "2025-01-10", 0.0, reason="vacation")
    rows = store.list_availability(r["id"])
    assert len(rows) == 1
    assert rows[0]["hours_per_day"] == 0.0


def test_add_task_and_get(store):
    t = store.add_task("acme", "Design API", estimate_hours=16)
    assert store.get_task(t["id"])["title"] == "Design API"


def test_update_task(store):
    t = store.add_task("acme", "Design API")
    updated = store.update_task(t["id"], estimate_hours=8.0, status="in-progress")
    assert updated["estimate_hours"] == 8.0
    assert updated["status"] == "in-progress"


def test_list_tasks_project_scoped(store):
    store.add_task("acme", "A")
    store.add_task("other", "B")
    assert [t["title"] for t in store.list_tasks("acme")] == ["A"]


def test_add_dependency_and_list(store):
    a = store.add_task("acme", "A")
    b = store.add_task("acme", "B")
    store.add_dependency(a["id"], b["id"], "FS", 1.0)
    deps = store.list_dependencies("acme")
    assert deps == [{"predecessor_id": a["id"], "successor_id": b["id"], "type": "FS", "lag_days": 1.0}]


def test_add_dependency_rejects_direct_cycle(store):
    a = store.add_task("acme", "A")
    b = store.add_task("acme", "B")
    store.add_dependency(a["id"], b["id"])
    with pytest.raises(CyclicDependencyError):
        store.add_dependency(b["id"], a["id"])


def test_add_dependency_rejects_self_cycle(store):
    a = store.add_task("acme", "A")
    with pytest.raises(CyclicDependencyError):
        store.add_dependency(a["id"], a["id"])


def test_add_dependency_rejects_transitive_cycle(store):
    a = store.add_task("acme", "A")
    b = store.add_task("acme", "B")
    c = store.add_task("acme", "C")
    store.add_dependency(a["id"], b["id"])
    store.add_dependency(b["id"], c["id"])
    with pytest.raises(CyclicDependencyError):
        store.add_dependency(c["id"], a["id"])


def test_scenario_and_change_roundtrip(store):
    scenario = store.add_scenario("acme", "Base plan", "baseline")
    store.add_scenario_change(scenario["id"], "task", 1, "estimate_hours", "20")
    changes = store.list_scenario_changes(scenario["id"])
    assert changes[0]["field"] == "estimate_hours"
    assert changes[0]["value"] == "20"


def test_latest_scenario_by_kind(store):
    store.add_scenario("acme", "First", "baseline")
    second = store.add_scenario("acme", "Second", "baseline")
    assert store.latest_scenario("acme")["id"] == second["id"]
    assert store.latest_scenario("acme", kind="whatif") is None


def test_allocation_and_schedule_roundtrip(store):
    scenario = store.add_scenario("acme", "Plan", "baseline")
    t = store.add_task("acme", "A")
    r = store.add_resource("acme", "Anna")
    store.add_allocation(scenario["id"], t["id"], r["id"], "2025-01-06", "2025-01-07", 8.0)
    store.set_schedule_row(
        scenario["id"], t["id"], earliest_start="2025-01-06", earliest_finish="2025-01-07",
        latest_start="2025-01-06", latest_finish="2025-01-07", slack_days=0, is_critical=True,
    )
    assert len(store.list_allocations(scenario["id"])) == 1
    assert store.list_schedule(scenario["id"])[0]["is_critical"] == 1


def test_clear_allocation_and_schedule(store):
    scenario = store.add_scenario("acme", "Plan", "baseline")
    t = store.add_task("acme", "A")
    r = store.add_resource("acme", "Anna")
    store.add_allocation(scenario["id"], t["id"], r["id"], "2025-01-06", "2025-01-07", 8.0)
    store.set_schedule_row(
        scenario["id"], t["id"], earliest_start="2025-01-06", earliest_finish="2025-01-07",
        latest_start="2025-01-06", latest_finish="2025-01-07", slack_days=0, is_critical=True,
    )
    store.clear_allocation(scenario["id"])
    store.clear_schedule(scenario["id"])
    assert store.list_allocations(scenario["id"]) == []
    assert store.list_schedule(scenario["id"]) == []


def test_commit_scenario_marks_committed_and_freezes_baseline(store):
    scenario = store.add_scenario("acme", "Plan", "baseline")
    t = store.add_task("acme", "A")
    r = store.add_resource("acme", "Anna")
    store.add_allocation(scenario["id"], t["id"], r["id"], "2025-01-06", "2025-01-07", 8.0)
    store.set_schedule_row(
        scenario["id"], t["id"], earliest_start="2025-01-06", earliest_finish="2025-01-07",
        latest_start="2025-01-06", latest_finish="2025-01-07", slack_days=0, is_critical=True,
    )
    result = store.commit_scenario(scenario["id"], "alice")

    committed = store.get_scenario(scenario["id"])
    assert committed["kind"] == "committed"
    assert committed["committed_by"] == "alice"

    baseline = store.get_scenario(result["baseline_scenario_id"])
    assert baseline["kind"] == "baseline"
    assert baseline["parent_id"] == scenario["id"]
    assert len(store.list_allocations(baseline["id"])) == 1
    assert len(store.list_schedule(baseline["id"])) == 1


def test_commit_unknown_scenario_raises(store):
    with pytest.raises(ValueError):
        store.commit_scenario(999, "alice")


def test_actual_roundtrip(store):
    t = store.add_task("acme", "A")
    store.add_actual(t["id"], "2025-01-06", hours_logged=4.0, percent_complete=50.0)
    actuals = store.list_actuals(t["id"])
    assert actuals[0]["hours_logged"] == 4.0
