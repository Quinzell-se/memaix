# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for timeline.inverse builders."""

from __future__ import annotations

from memaix_gateway.timeline.inverse import TOOL_HANDLERS


def test_memory_write_inverse_targets_revert():
    summary_fn, inverse_fn = TOOL_HANDLERS["memory_write"]
    tail = ("notes/x.md", "hello")
    result = {"path": "notes/x.md", "commit": "abc123"}
    inverse = inverse_fn(tail, {}, result)
    assert inverse == {"tool": "memory_revert", "args": {"commit": "abc123"}}
    assert "notes/x.md" in summary_fn(tail, {}, result)


def test_memory_write_inverse_none_without_commit():
    _, inverse_fn = TOOL_HANDLERS["memory_write"]
    assert inverse_fn(("note.md",), {}, {}) is None


def test_calendar_create_inverse_targets_delete():
    summary_fn, inverse_fn = TOOL_HANDLERS["calendar_create"]
    tail = ("Standup", "2026-01-01T09:00", "2026-01-01T09:15")
    result = {"id": "ev-1", "title": "Standup"}
    inverse = inverse_fn(tail, {}, result)
    assert inverse == {"tool": "calendar_delete", "args": {"id": "ev-1"}}
    assert "Standup" in summary_fn(tail, {}, result)


def test_calendar_create_inverse_none_without_id():
    _, inverse_fn = TOOL_HANDLERS["calendar_create"]
    assert inverse_fn(("Standup",), {}, {}) is None


def test_backlog_add_inverse_targets_reject_at_version_1():
    summary_fn, inverse_fn = TOOL_HANDLERS["backlog_add"]
    tail = ("New idea", "description text")
    result = {"id": "a1b2c3d4", "status": "inbox"}
    inverse = inverse_fn(tail, {}, result)
    assert inverse == {
        "tool": "backlog_set_status",
        "args": {"id": "a1b2c3d4", "status": "rejected", "expected_version": 1},
    }
    assert "New idea" in summary_fn(tail, {}, result)
    assert "a1b2c3d4" in summary_fn(tail, {}, result)


def test_backlog_add_inverse_none_without_id():
    _, inverse_fn = TOOL_HANDLERS["backlog_add"]
    assert inverse_fn(("title",), {}, {}) is None


def test_memory_append_uses_shared_inverse_builder():
    summary_fn, inverse_fn = TOOL_HANDLERS["memory_append"]
    result = {"path": "x.md", "commit": "def456"}
    assert inverse_fn(("x.md", "more text"), {}, result) == {
        "tool": "memory_revert", "args": {"commit": "def456"}
    }


def test_backlog_set_status_has_no_registered_inverse():
    """Field-level undo needs a pre-image we don't capture — scoped out of v1."""
    assert "backlog_set_status" not in TOOL_HANDLERS
    assert "calendar_update" not in TOOL_HANDLERS
