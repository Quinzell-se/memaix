# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for pm.schedule.compute_schedule — critical-path method
(FEATURE-PM-ENGINE.md §4)."""

from __future__ import annotations

from datetime import date

import pytest

from memaix_gateway.pm.schedule import CyclicTaskGraphError, compute_schedule

START = date(2025, 1, 6)  # a Monday; v1 has no weekend calendar so this doesn't matter


def _by_id(rows):
    return {r["task_id"]: r for r in rows}


def test_single_task_no_dependencies():
    tasks = [{"id": 1, "estimate_hours": 16}]
    rows = _by_id(compute_schedule(tasks, [], project_start=START))
    assert rows[1]["earliest_start"] == "2025-01-06"
    assert rows[1]["earliest_finish"] == "2025-01-08"  # 16h / 8h-per-day = 2 days
    assert rows[1]["slack_days"] == 0
    assert rows[1]["is_critical"] is True


def test_linear_chain_is_all_critical():
    tasks = [{"id": 1, "estimate_hours": 8}, {"id": 2, "estimate_hours": 8}, {"id": 3, "estimate_hours": 8}]
    deps = [
        {"predecessor_id": 1, "successor_id": 2, "type": "FS", "lag_days": 0},
        {"predecessor_id": 2, "successor_id": 3, "type": "FS", "lag_days": 0},
    ]
    rows = _by_id(compute_schedule(tasks, deps, project_start=START))
    assert all(r["is_critical"] for r in rows.values())
    assert rows[1]["earliest_finish"] == rows[2]["earliest_start"]
    assert rows[2]["earliest_finish"] == rows[3]["earliest_start"]


def test_parallel_paths_only_longest_is_critical():
    # 1 -> 3 (short path, 1 day), 2 -> 3 (long path, 3 days); 3 depends on both.
    tasks = [
        {"id": 1, "estimate_hours": 8},   # 1 day
        {"id": 2, "estimate_hours": 24},  # 3 days
        {"id": 3, "estimate_hours": 8},
    ]
    deps = [
        {"predecessor_id": 1, "successor_id": 3, "type": "FS", "lag_days": 0},
        {"predecessor_id": 2, "successor_id": 3, "type": "FS", "lag_days": 0},
    ]
    rows = _by_id(compute_schedule(tasks, deps, project_start=START))
    assert rows[2]["is_critical"] is True
    assert rows[1]["is_critical"] is False
    assert rows[1]["slack_days"] == 2  # 3 days - 1 day
    assert rows[3]["earliest_start"] == rows[2]["earliest_finish"]


def test_lag_days_respected():
    tasks = [{"id": 1, "estimate_hours": 8}, {"id": 2, "estimate_hours": 8}]
    deps = [{"predecessor_id": 1, "successor_id": 2, "type": "FS", "lag_days": 5}]
    rows = _by_id(compute_schedule(tasks, deps, project_start=START))
    assert rows[2]["earliest_start"] == "2025-01-12"  # finish (01-07) + 5 days lag


def test_cycle_raises_clear_error():
    tasks = [{"id": 1, "estimate_hours": 8}, {"id": 2, "estimate_hours": 8}]
    deps = [
        {"predecessor_id": 1, "successor_id": 2, "type": "FS", "lag_days": 0},
        {"predecessor_id": 2, "successor_id": 1, "type": "FS", "lag_days": 0},
    ]
    with pytest.raises(CyclicTaskGraphError):
        compute_schedule(tasks, deps, project_start=START)


def test_task_with_no_estimate_has_zero_duration():
    tasks = [{"id": 1, "estimate_hours": None}, {"id": 2, "estimate_hours": 8}]
    deps = [{"predecessor_id": 1, "successor_id": 2, "type": "FS", "lag_days": 0}]
    rows = _by_id(compute_schedule(tasks, deps, project_start=START))
    assert rows[1]["earliest_start"] == rows[1]["earliest_finish"]
    assert rows[2]["earliest_start"] == rows[1]["earliest_finish"]


def test_ss_dependency_type():
    tasks = [{"id": 1, "estimate_hours": 24}, {"id": 2, "estimate_hours": 8}]
    deps = [{"predecessor_id": 1, "successor_id": 2, "type": "SS", "lag_days": 1}]
    rows = _by_id(compute_schedule(tasks, deps, project_start=START))
    # successor may start 1 day after predecessor starts, regardless of predecessor's 3-day duration
    assert rows[2]["earliest_start"] == "2025-01-07"


def test_empty_task_list_returns_empty():
    assert compute_schedule([], [], project_start=START) == []
