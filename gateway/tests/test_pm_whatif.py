# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for pm.whatif.whatif — consequence analysis without touching the
committed plan (FEATURE-PM-ENGINE.md §4)."""

from __future__ import annotations

from datetime import date

import pytest

from memaix_gateway.pm.allocate import allocate
from memaix_gateway.pm.store import PMStore
from memaix_gateway.pm.whatif import whatif

START = date(2025, 1, 6)


@pytest.fixture()
def store(tmp_path):
    return PMStore.for_path(tmp_path / "pm.db")


def test_whatif_creates_a_new_scenario_without_touching_base(store):
    scenario = store.add_scenario("acme", "Plan", "baseline")
    store.add_resource("acme", "Anna", capacity_hours_per_day=8.0)
    t = store.add_task("acme", "Task", estimate_hours=8)
    allocate(store, scenario["id"], project_start=START)
    base_schedule_before = store.list_schedule(scenario["id"])

    result = whatif(store, scenario["id"], [{"entity": "task", "entity_id": t["id"], "field": "estimate_hours", "value": 40}], project_start=START)

    assert result["whatif_scenario_id"] != scenario["id"]
    # Base scenario's own stored schedule is untouched.
    assert store.list_schedule(scenario["id"]) == base_schedule_before


def test_whatif_increasing_estimate_pushes_finish_later(store):
    scenario = store.add_scenario("acme", "Plan", "baseline")
    store.add_resource("acme", "Anna", capacity_hours_per_day=8.0)
    t = store.add_task("acme", "Task", estimate_hours=8)
    allocate(store, scenario["id"], project_start=START)

    result = whatif(
        store, scenario["id"],
        [{"entity": "task", "entity_id": t["id"], "field": "estimate_hours", "value": 40}],
        project_start=START,
    )

    assert len(result["schedule_changes"]) == 1
    change = result["schedule_changes"][0]
    assert change["task_id"] == t["id"]
    assert change["whatif_finish"] > change["base_finish"]


def test_whatif_removing_resource_reassigns_or_unallocates_task(store):
    scenario = store.add_scenario("acme", "Plan", "baseline")
    skill = store.get_or_create_skill("acme", "python")
    anna = store.add_resource("acme", "Anna")
    store.set_resource_skill(anna["id"], skill["id"])
    t = store.add_task("acme", "Task", estimate_hours=8, required_skill_id=skill["id"])
    allocate(store, scenario["id"], project_start=START)

    result = whatif(
        store, scenario["id"],
        [{"entity": "resource", "entity_id": anna["id"], "field": "active", "value": False}],
        project_start=START,
    )

    assert len(result["resource_changes"]) == 1
    assert result["resource_changes"][0]["whatif_resource_id"] is None
    assert any("no eligible resource" in w for w in result["warnings"])


def test_whatif_reports_milestone_shift(store):
    scenario = store.add_scenario("acme", "Plan", "baseline")
    store.add_resource("acme", "Anna", capacity_hours_per_day=8.0)
    m = store.add_milestone("acme", "Launch", target_date="2025-01-10")
    t = store.add_task("acme", "Task", estimate_hours=8, milestone_id=m["id"])
    allocate(store, scenario["id"], project_start=START)

    result = whatif(
        store, scenario["id"],
        [{"entity": "task", "entity_id": t["id"], "field": "estimate_hours", "value": 80}],
        project_start=START,
    )

    assert len(result["milestone_changes"]) == 1
    assert result["milestone_changes"][0]["milestone_id"] == m["id"]


def test_whatif_no_change_reports_empty_diff(store):
    scenario = store.add_scenario("acme", "Plan", "baseline")
    store.add_resource("acme", "Anna", capacity_hours_per_day=8.0)
    store.add_task("acme", "Task", estimate_hours=8)
    allocate(store, scenario["id"], project_start=START)

    result = whatif(store, scenario["id"], [], project_start=START)

    assert result["schedule_changes"] == []
    assert result["resource_changes"] == []
    assert result["milestone_changes"] == []


def test_whatif_unknown_base_scenario_raises(store):
    with pytest.raises(ValueError):
        whatif(store, 999, [])


def test_whatif_does_not_affect_a_second_whatif(store):
    scenario = store.add_scenario("acme", "Plan", "baseline")
    store.add_resource("acme", "Anna", capacity_hours_per_day=8.0)
    t = store.add_task("acme", "Task", estimate_hours=8)
    allocate(store, scenario["id"], project_start=START)

    r1 = whatif(store, scenario["id"], [{"entity": "task", "entity_id": t["id"], "field": "priority", "value": 1}], project_start=START)
    r2 = whatif(store, scenario["id"], [{"entity": "task", "entity_id": t["id"], "field": "estimate_hours", "value": 16}], project_start=START)

    assert r1["whatif_scenario_id"] != r2["whatif_scenario_id"]
