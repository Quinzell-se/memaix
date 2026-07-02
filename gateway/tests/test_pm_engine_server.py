# SPDX-License-Identifier: AGPL-3.0-or-later
"""Server-level tests for the PM planning-engine MCP tools
(FEATURE-PM-ENGINE.md §5) — RBAC, audit, and an end-to-end
resource->task->allocate->utilization->commit->variance flow."""

from __future__ import annotations

import pytest

from memaix_gateway import server
from memaix_gateway.acl import AccessDenied, Acl
from memaix_gateway.outbox.queue import ActionQueue
from memaix_gateway.pm.store import PMStore
from memaix_gateway.safety.audit import AuditLog
from memaix_gateway.notify.store import NotifyStore
from memaix_gateway.rules.store import RulesStore
from memaix_gateway.search.store import EmbeddingStore
from memaix_gateway.timeline.store import ActionsStore


@pytest.fixture()
def wired(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    (vault / "backlog").mkdir(parents=True)
    acl = Acl(
        users={
            "alice": {"grants": {"proj": "owner", "other": "owner"}},
            "bob": {"grants": {"proj": "reader"}},
            "carol": {"grants": {"proj": "collaborator"}},
        },
        projects={"proj": {"vault": str(vault)}, "other": {"vault": str(tmp_path / "other-vault")}},
    )
    AuditLog._clear_instances()
    monkeypatch.setattr(server, "_acl", acl)
    monkeypatch.setattr(server, "_audit", AuditLog.for_path(tmp_path / "audit.db"))
    monkeypatch.setattr(server, "_outbox_queue", ActionQueue.for_path(tmp_path / "outbox.db"))
    monkeypatch.setattr(server, "_timeline_store", ActionsStore.for_path(tmp_path / "actions.db"))
    monkeypatch.setattr(server, "_search_store", EmbeddingStore.for_path(tmp_path / "index.db"))
    monkeypatch.setattr(server, "_search_embedder", None)
    monkeypatch.setattr(server, "_search_embedder_loaded", True)
    monkeypatch.setattr(server, "_notify_store", NotifyStore.for_path(tmp_path / "notify.db"))
    monkeypatch.setattr(server, "_rules_store", RulesStore.for_path(tmp_path / "rules.db"))
    monkeypatch.setattr(server, "_pm_store", PMStore.for_path(tmp_path / "pm.db"))
    monkeypatch.setenv("MEMAIX_USER", "alice")
    server._rate_limiter._windows.clear()
    return vault, acl


def test_full_plan_flow(wired):
    resource = server.resource_add("proj", "Anna", capacity_hours_per_day=8.0)
    task = server.task_add("proj", "Design API", estimate_hours=16)
    scenario = server.scenario_add("proj", "Sprint 1")

    result = server.pm_allocate("proj", scenario["id"], "2025-01-06")
    assert result["warnings"] == []
    assert len(result["allocations"]) == 1
    assert result["allocations"][0]["resource_id"] == resource["id"]

    util = server.pm_utilization("proj", scenario["id"], "2025-01-06", "2025-01-07")
    assert util["resources"][0]["utilization_pct"] == 100.0

    commit_result = server.plan_commit("proj", scenario["id"])
    assert commit_result["committed_scenario_id"] == scenario["id"]

    server.task_log_actual("proj", task["id"], "2025-01-06", hours_logged=16.0, percent_complete=100.0)
    variance = server.pm_variance("proj")
    assert variance["ok"] is True
    assert variance["tasks"][0]["percent_complete"] == 100.0


def test_dependency_add_rejects_cycle(wired):
    a = server.task_add("proj", "A")
    b = server.task_add("proj", "B")
    server.dependency_add("proj", a["id"], b["id"])
    with pytest.raises(ValueError):
        server.dependency_add("proj", b["id"], a["id"])


def test_resource_add_requires_owner(wired, monkeypatch):
    monkeypatch.setenv("MEMAIX_USER", "carol")  # collaborator
    with pytest.raises(AccessDenied):
        server.resource_add("proj", "Anna")


def test_task_add_allows_collaborator(wired, monkeypatch):
    monkeypatch.setenv("MEMAIX_USER", "carol")
    task = server.task_add("proj", "Some task")
    assert task["title"] == "Some task"


def test_reader_cannot_allocate(wired, monkeypatch):
    scenario = server.scenario_add("proj", "Sprint 1")
    monkeypatch.setenv("MEMAIX_USER", "bob")  # reader
    with pytest.raises(AccessDenied):
        server.pm_allocate("proj", scenario["id"])


def test_reader_can_list_resources_and_run_utilization_variance(wired, monkeypatch):
    scenario = server.scenario_add("proj", "Sprint 1")
    server.resource_add("proj", "Anna")
    server.task_add("proj", "Task", estimate_hours=8)
    server.pm_allocate("proj", scenario["id"], "2025-01-06")

    monkeypatch.setenv("MEMAIX_USER", "bob")
    assert server.resource_list("proj") != []
    server.pm_utilization("proj", scenario["id"], "2025-01-06", "2025-01-07")
    server.pm_variance("proj")  # no baseline yet — should not raise, just {"ok": False}


def test_plan_commit_requires_owner(wired, monkeypatch):
    scenario = server.scenario_add("proj", "Sprint 1")
    monkeypatch.setenv("MEMAIX_USER", "carol")
    with pytest.raises(AccessDenied):
        server.plan_commit("proj", scenario["id"])


def test_task_add_and_resource_add_are_audited(wired):
    server.task_add("proj", "Task")
    server.resource_add("proj", "Anna")
    tools = [e["tool"] for e in server._get_audit().tail(10)]
    assert "task_add" in tools
    assert "resource_add" in tools


def test_scenario_scoped_to_own_project(wired):
    scenario = server.scenario_add("proj", "Sprint 1")
    # A scenario created under "proj" must not be usable from "other".
    with pytest.raises(FileNotFoundError):
        server.pm_allocate("other", scenario["id"])


def test_resource_availability_and_skill(wired):
    r = server.resource_add("proj", "Anna")
    server.resource_availability("proj", r["id"], "2025-01-06", "2025-01-06", 0.0, "holiday")
    result = server.resource_set_skill("proj", r["id"], "python", 4)
    assert result["skill"] == "python"


def test_milestone_add(wired):
    m = server.milestone_add("proj", "Beta launch", "2025-03-01")
    assert m["name"] == "Beta launch"


def test_pm_variance_today_override(wired):
    server.resource_add("proj", "Anna", capacity_hours_per_day=8.0)
    task = server.task_add("proj", "Task", estimate_hours=8)
    scenario = server.scenario_add("proj", "Sprint 1")
    server.pm_allocate("proj", scenario["id"], "2025-01-06")
    server.plan_commit("proj", scenario["id"])
    server.task_log_actual("proj", task["id"], "2025-01-06", percent_complete=50.0)

    result = server.pm_variance("proj", today="2025-01-20")
    assert result["tasks"][0]["slippage_days"] == 13  # planned finish 2025-01-07 -> 13 days late


def test_pm_whatif_diffs_without_touching_base(wired):
    server.resource_add("proj", "Anna", capacity_hours_per_day=8.0)
    task = server.task_add("proj", "Task", estimate_hours=8)
    scenario = server.scenario_add("proj", "Sprint 1")
    server.pm_allocate("proj", scenario["id"], "2025-01-06")
    base_schedule_before = server._get_pm().list_schedule(scenario["id"])

    result = server.pm_whatif(
        "proj", scenario["id"], [{"entity": "task", "entity_id": task["id"], "field": "estimate_hours", "value": 40}],
        "2025-01-06",
    )

    assert result["whatif_scenario_id"] != scenario["id"]
    assert len(result["schedule_changes"]) == 1
    assert server._get_pm().list_schedule(scenario["id"]) == base_schedule_before


def test_pm_whatif_collaborator_allowed(wired, monkeypatch):
    server.resource_add("proj", "Anna", capacity_hours_per_day=8.0)
    task = server.task_add("proj", "Task", estimate_hours=8)
    scenario = server.scenario_add("proj", "Sprint 1")
    server.pm_allocate("proj", scenario["id"], "2025-01-06")

    monkeypatch.setenv("MEMAIX_USER", "carol")  # collaborator, not owner
    result = server.pm_whatif(
        "proj", scenario["id"], [{"entity": "task", "entity_id": task["id"], "field": "priority", "value": 1}], None,
    )
    assert result["whatif_scenario_id"] != scenario["id"]


def test_pm_whatif_reader_denied(wired, monkeypatch):
    scenario = server.scenario_add("proj", "Sprint 1")
    monkeypatch.setenv("MEMAIX_USER", "bob")
    with pytest.raises(AccessDenied):
        server.pm_whatif("proj", scenario["id"], [], None)


def test_pm_whatif_rejects_unsupported_field(wired):
    task = server.task_add("proj", "Task", estimate_hours=8)
    scenario = server.scenario_add("proj", "Sprint 1")
    with pytest.raises(ValueError):
        server.pm_whatif("proj", scenario["id"], [{"entity": "task", "entity_id": task["id"], "field": "title", "value": "Hacked"}], None)


def test_pm_whatif_rejects_task_from_other_project(wired):
    other_task = server.task_add("other", "Other task", estimate_hours=8)
    scenario = server.scenario_add("proj", "Sprint 1")
    with pytest.raises(FileNotFoundError):
        server.pm_whatif(
            "proj", scenario["id"],
            [{"entity": "task", "entity_id": other_task["id"], "field": "estimate_hours", "value": 10}], None,
        )


# ------------------------------------------------------------------
# pm_report (FEATURE-PM-ENGINE.md §5)
# ------------------------------------------------------------------


def test_pm_report_status_bundles_milestones_variance_raid(wired):
    server.milestone_add("proj", "Beta launch", "2025-01-01")  # in the past -> overdue
    server.resource_add("proj", "Anna", capacity_hours_per_day=8.0)
    server.task_add("proj", "Task", estimate_hours=8)
    scenario = server.scenario_add("proj", "Sprint 1")
    server.pm_allocate("proj", scenario["id"], "2025-01-06")
    server.plan_commit("proj", scenario["id"])
    server.pm_raid_add("proj", "Risk", "Vendor delay")

    result = server.pm_report("proj")

    assert result["kind"] == "status"
    assert result["audience"] == "team"
    assert result["milestones"][0]["name"] == "Beta launch"
    assert result["milestones"][0]["overdue"] is True
    assert result["variance"]["ok"] is True
    assert result["raid"]["count"] == 1


def test_pm_report_leadership_condenses_milestones_to_overdue(wired):
    server.milestone_add("proj", "On track", "2999-01-01")
    server.milestone_add("proj", "Late", "2025-01-01")

    result = server.pm_report("proj", kind="milestones", audience="leadership")

    names = [m["name"] for m in result["milestones"]]
    assert names == ["Late"]


def test_pm_report_leadership_condenses_raid_to_high_severity(wired):
    server.pm_raid_add("proj", "Risk", "Minor thing", severity="low")
    server.pm_raid_add("proj", "Issue", "Big problem", severity="high")

    result = server.pm_report("proj", kind="raid", audience="leadership")

    assert result["raid"]["count"] == 1
    assert result["raid"]["entries"][0]["summary"] == "Big problem"


def test_pm_report_utilization_requires_scenario_and_period(wired):
    with pytest.raises(ValueError):
        server.pm_report("proj", kind="utilization")


def test_pm_report_utilization_kind(wired):
    server.resource_add("proj", "Anna", capacity_hours_per_day=8.0)
    server.task_add("proj", "Task", estimate_hours=8)
    scenario = server.scenario_add("proj", "Sprint 1")
    server.pm_allocate("proj", scenario["id"], "2025-01-06")

    result = server.pm_report(
        "proj", kind="utilization", scenario_id=scenario["id"],
        period_start="2025-01-06", period_end="2025-01-06",
    )
    assert result["utilization"]["resources"][0]["utilization_pct"] == 100.0


def test_pm_report_rejects_unknown_kind(wired):
    with pytest.raises(ValueError):
        server.pm_report("proj", kind="bogus")


def test_pm_report_rejects_unknown_audience(wired):
    with pytest.raises(ValueError):
        server.pm_report("proj", audience="bogus")


def test_pm_report_reader_allowed(wired, monkeypatch):
    server.milestone_add("proj", "Beta", "2025-01-01")
    monkeypatch.setenv("MEMAIX_USER", "bob")
    result = server.pm_report("proj", kind="milestones")
    assert result["milestones"][0]["name"] == "Beta"


# ------------------------------------------------------------------
# Security-fix regressions
# ------------------------------------------------------------------


def test_task_add_rejects_milestone_from_other_project(wired):
    other_ms = server.milestone_add("other", "Other milestone", "2025-03-01")
    with pytest.raises(FileNotFoundError):
        server.task_add("proj", "Task", milestone_id=other_ms["id"])


def test_outbox_get_denies_reader_and_allows_owner(wired, monkeypatch):
    # Queue an email_send action in proj (recipients/body live in the args).
    action_id = server._get_outbox().enqueue(
        "alice", "proj", "email_send",
        {"to": "x@y.com", "subject": "secret", "body": "confidential"}, "preview",
    )
    # bob is a reader on proj — must NOT be able to read the queued email body
    # (email_send approval requires owner).
    monkeypatch.setenv("MEMAIX_USER", "bob")
    with pytest.raises(AccessDenied):
        server.outbox_get(action_id)
    assert server.outbox_list("proj") == []

    # alice is owner — can see it.
    monkeypatch.setenv("MEMAIX_USER", "alice")
    assert server.outbox_get(action_id)["id"] == action_id
    assert any(a["id"] == action_id for a in server.outbox_list("proj"))
