# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for outbox.preview.render_preview."""

from __future__ import annotations

from memaix_gateway.outbox.preview import render_preview


def test_email_preview_contains_key_fields():
    p = render_preview(
        "email_send", {"to": "x@y.com", "cc": "z@y.com", "subject": "Hej", "body": "Innehåll"}
    )
    assert "x@y.com" in p
    assert "z@y.com" in p
    assert "Hej" in p
    assert "Innehåll" in p


def test_email_preview_truncates_long_body():
    body = "x" * 1000
    p = render_preview("email_send", {"to": "a@b.com", "subject": "s", "body": body})
    assert len(p) < 1000
    assert p.rstrip().endswith("…")


def test_calendar_create_preview():
    p = render_preview(
        "calendar_create",
        {"title": "Standup", "start": "2026-01-01T09:00", "end": "2026-01-01T09:15",
         "attendees": ["a@b.com"], "location": "Room 1"},
    )
    assert "Standup" in p
    assert "2026-01-01T09:00" in p
    assert "Room 1" in p
    assert "a@b.com" in p


def test_calendar_update_preview_missing_fields_ok():
    p = render_preview("calendar_update", {"id": "ev-1"})
    assert isinstance(p, str)


def test_unknown_tool_falls_back_to_generic():
    p = render_preview("some_future_tool", {"a": 1, "b": "x"})
    assert "some_future_tool" in p
