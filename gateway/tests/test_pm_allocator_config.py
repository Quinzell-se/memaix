# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for tools.pm_engine's config-driven allocator selection
(FEATURE-PM-ENGINE.md Byggordning steg 7/8: `pm.allocator: heuristic|cpsat`).
"""

from __future__ import annotations

import pytest

from memaix_gateway.acl import Acl
from memaix_gateway.pm.allocate import allocate
from memaix_gateway.pm.store import PMStore
from memaix_gateway.tools.pm_engine import _resolve_allocator, pm_allocate, pm_whatif


def test_resolve_allocator_defaults_to_heuristic():
    assert _resolve_allocator({}) is allocate


def test_resolve_allocator_heuristic_explicit():
    assert _resolve_allocator({"memaix": {"pm": {"allocator": "heuristic"}}}) is allocate


def test_resolve_allocator_rejects_unknown_name():
    with pytest.raises(ValueError):
        _resolve_allocator({"memaix": {"pm": {"allocator": "bogus"}}})


def test_resolve_allocator_cpsat():
    pytest.importorskip("ortools")
    from memaix_gateway.pm.allocate_cpsat import allocate_cpsat

    assert _resolve_allocator({"memaix": {"pm": {"allocator": "cpsat"}}}) is allocate_cpsat


@pytest.fixture()
def acl(tmp_path):
    vault = tmp_path / "vault"
    (vault / "backlog").mkdir(parents=True)
    return Acl(users={"alice": {"grants": {"proj": "owner"}}}, projects={"proj": {"vault": str(vault)}})


@pytest.fixture()
def store(tmp_path):
    return PMStore.for_path(tmp_path / "pm.db")


def test_pm_allocate_uses_cpsat_when_configured(acl, store):
    pytest.importorskip("ortools")
    store.add_resource("proj", "Anna", capacity_hours_per_day=8.0)
    store.add_task("proj", "Design", estimate_hours=16)
    scenario = store.add_scenario("proj", "Sprint 1", "baseline")

    result = pm_allocate(
        acl, "alice", "proj", scenario["id"], "2025-01-06",
        _pm=store, _cfg={"memaix": {"pm": {"allocator": "cpsat"}}},
    )

    assert result["allocations"][0]["end_date"] == "2025-01-07"


def test_pm_allocate_defaults_to_heuristic(acl, store):
    store.add_resource("proj", "Anna", capacity_hours_per_day=8.0)
    store.add_task("proj", "Design", estimate_hours=16)
    scenario = store.add_scenario("proj", "Sprint 1", "baseline")

    result = pm_allocate(acl, "alice", "proj", scenario["id"], "2025-01-06", _pm=store, _cfg={})

    assert result["allocations"][0]["end_date"] == "2025-01-07"


def test_pm_whatif_uses_configured_allocator(acl, store):
    pytest.importorskip("ortools")
    store.add_resource("proj", "Anna", capacity_hours_per_day=8.0)
    task = store.add_task("proj", "Design", estimate_hours=8)
    scenario = store.add_scenario("proj", "Sprint 1", "baseline")
    pm_allocate(acl, "alice", "proj", scenario["id"], "2025-01-06", _pm=store, _cfg={})

    result = pm_whatif(
        acl, "alice", "proj", scenario["id"],
        [{"entity": "task", "entity_id": task["id"], "field": "estimate_hours", "value": 16}],
        "2025-01-06", _pm=store, _cfg={"memaix": {"pm": {"allocator": "cpsat"}}},
    )

    assert result["whatif_scenario_id"] != scenario["id"]
    assert len(result["schedule_changes"]) == 1
