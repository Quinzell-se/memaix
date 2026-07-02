# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for notify.brief.build."""

from __future__ import annotations

from datetime import datetime, timezone

from memaix_gateway.acl import Acl
from memaix_gateway.notify.brief import build


def _acl():
    return Acl(
        users={"alice": {"grants": {"proj": "owner"}}},
        projects={"proj": {"vault": "/v", "mailbox": {"host": "h"}, "calendar": {"url": "x"}}},
    )


def _prefs(**overrides):
    base = {"enabled": True, "timezone": "UTC", "brief_time": "07:00", "channels": [], "projects": ["proj"]}
    base.update(overrides)
    return base


NOW = datetime(2026, 1, 15, 7, 0, tzinfo=timezone.utc)


def test_build_includes_calendar_event():
    tools = {"calendar_events": lambda acl, u, p, s, e: [{"title": "Standup", "start": "09:00"}]}
    result = build(_acl(), "alice", None, _prefs(), now=NOW, tools=tools)
    assert "Standup" in result["markdown"]
    assert not result["empty"]


def test_build_includes_unread_mail_only():
    tools = {"email_list": lambda acl, u, p, f, lim: [
        {"subject": "Seen one", "from": "a@b.com", "seen": True},
        {"subject": "New invoice", "from": "c@d.com", "seen": False},
    ]}
    result = build(_acl(), "alice", None, _prefs(), now=NOW, tools=tools)
    assert "New invoice" in result["markdown"]
    assert "Seen one" not in result["markdown"]


def test_build_includes_backlog_changes_since_last_run():
    tools = {"backlog_list": lambda acl, u, p: [
        {"id": "a1", "title": "Old item", "status": "done", "updated_at": "2026-01-01T00:00:00"},
        {"id": "b2", "title": "New item", "status": "in-dev", "updated_at": "2026-01-15T06:00:00"},
    ]}
    result = build(_acl(), "alice", None, _prefs(), now=NOW, tools=tools, last_run_iso="2026-01-10T00:00:00")
    assert "New item" in result["markdown"]
    assert "Old item" not in result["markdown"]


def test_build_counts_open_raid():
    tools = {"pm_raid_list": lambda acl, u, p: {"entries": [{"status": "open"}, {"status": "closed"}, {"status": "open"}]}}
    result = build(_acl(), "alice", None, _prefs(), now=NOW, tools=tools)
    assert "2" in result["markdown"]


def test_build_empty_sends_when_send_when_empty_true():
    result = build(_acl(), "alice", None, _prefs(), now=NOW, tools={})
    assert result["empty"] is True
    assert result["markdown"]  # still has content ("Inget planerat" etc.)


def test_build_empty_skips_when_send_when_empty_false():
    cfg = {"memaix": {"brief": {"send_when_empty": False}}}
    result = build(_acl(), "alice", cfg, _prefs(), now=NOW, tools={})
    assert result["empty"] is True
    assert result["markdown"] == ""


def test_build_skips_project_without_matching_resource():
    tools = {"calendar_events": lambda *a: [{"title": "should not appear"}]}
    acl = Acl(users={"alice": {"grants": {"nocal": "owner"}}}, projects={"nocal": {"vault": "/v"}})
    result = build(acl, "alice", None, _prefs(projects=["nocal"]), now=NOW, tools=tools)
    assert "should not appear" not in result["markdown"]


def test_build_tool_exception_does_not_break_brief():
    def boom(*a):
        raise RuntimeError("imap down")

    tools = {"email_list": boom}
    result = build(_acl(), "alice", None, _prefs(), now=NOW, tools=tools)
    assert isinstance(result["markdown"], str)  # didn't raise


def test_build_max_mail_from_config():
    msgs = [{"subject": f"m{i}", "from": "x", "seen": False} for i in range(10)]
    tools = {"email_list": lambda acl, u, p, f, lim: msgs[:lim]}
    cfg = {"memaix": {"brief": {"max_mail": 2}}}
    result = build(_acl(), "alice", cfg, _prefs(), now=NOW, tools=tools)
    assert result["markdown"].count("- [proj] m") == 2
