# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the PM engine's agent-layer prompts (FEATURE-PM-ENGINE.md §6):
pm_plan_session, pm_whatif_session, and the extended pm_weekly_review.

Per the byggspec's own test requirement, these check that the prompt
strings state the determinism boundary (the LLM never computes a
schedule/date/consequence itself) and reference the engine's tools in the
right order — not that any LLM actually follows them (that's an eval-suite
concern, out of scope here)."""

from __future__ import annotations

from memaix_gateway import server


def test_pm_plan_session_states_determinism_boundary():
    text = server.pm_plan_session("proj")
    assert "never calculate" in text or "never compute" in text
    assert "engine" in text.lower()


def test_pm_plan_session_tool_order():
    text = server.pm_plan_session("proj")
    # resources/tasks captured before allocate; allocate before commit.
    # rindex, not index: the opening sentence name-drops the whole tool
    # chain in one parenthetical before the numbered steps use them in order.
    assert text.rindex("resource_add") < text.rindex("pm_allocate")
    assert text.rindex("task_add") < text.rindex("pm_allocate")
    assert text.rindex("pm_allocate") < text.rindex("plan_commit")


def test_pm_plan_session_requires_owner_for_commit():
    text = server.pm_plan_session("proj")
    assert "owner" in text.lower()


def test_pm_whatif_session_states_determinism_boundary():
    text = server.pm_whatif_session("proj")
    assert "never compute" in text or "never calculate" in text
    assert "engine" in text.lower()


def test_pm_whatif_session_tool_order():
    text = server.pm_whatif_session("proj")
    assert text.rindex("scenario_list") < text.rindex("pm_whatif")


def test_pm_whatif_session_documents_supported_change_fields():
    text = server.pm_whatif_session("proj")
    assert "estimate_hours" in text
    assert "priority" in text
    assert "required_skill_id" in text
    assert "active" in text


def test_pm_whatif_session_never_touches_committed_plan():
    text = server.pm_whatif_session("proj")
    assert "never" in text.lower() and "committed" in text.lower()


def test_pm_weekly_review_extended_with_engine_rollup():
    text = server.pm_weekly_review("proj")
    assert "pm_report" in text
    assert "pm_utilization" in text
