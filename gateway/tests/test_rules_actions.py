# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for rules.actions.run_action."""

from __future__ import annotations

from memaix_gateway.acl import Acl
from memaix_gateway.rules.actions import run_action


def _acl():
    return Acl(users={"alice": {"grants": {"proj": "owner"}}}, projects={"proj": {"vault": "/v"}})


def test_resolves_from_field_using_payload():
    calls = []

    def fake_backlog_add(acl, user, project, **kwargs):
        calls.append((project, kwargs))
        return {"id": "abc"}

    action = {"type": "backlog_add", "params": {"project": "proj", "title_from": "subject", "description_from": "body"}}
    payload = {"subject": "New feature request", "body": "details here"}
    result = run_action(_acl(), "alice", action, payload, tools={"backlog_add": fake_backlog_add})
    assert result["ok"] is True
    project, kwargs = calls[0]
    assert project == "proj"
    assert kwargs["title"] == "New feature request"
    assert kwargs["description"] == "details here"


def test_literal_params_pass_through_unchanged():
    calls = []

    def fake_pm_raid_add(acl, user, project, **kwargs):
        calls.append(kwargs)
        return {"ok": True}

    action = {"type": "pm_raid_add", "params": {"project": "proj", "raid_type": "Risk", "severity": "high"}}
    run_action(_acl(), "alice", action, {}, tools={"pm_raid_add": fake_pm_raid_add})
    assert calls[0]["raid_type"] == "Risk"
    assert calls[0]["severity"] == "high"


def test_missing_project_returns_error():
    action = {"type": "backlog_add", "params": {"title_from": "subject"}}
    result = run_action(_acl(), "alice", action, {"subject": "x"}, tools={})
    assert result["ok"] is False
    assert "project" in result["error"]


def test_unknown_action_type_returns_error():
    action = {"type": "carrier_pigeon", "params": {"project": "proj"}}
    result = run_action(_acl(), "alice", action, {}, tools={})
    assert result["ok"] is False
    assert "unknown action type" in result["error"]


def test_action_exception_is_caught_and_reported():
    def boom(acl, user, project, **kwargs):
        raise RuntimeError("smtp down")

    action = {"type": "email_send", "params": {"project": "proj", "to": "x@y.com"}}
    result = run_action(_acl(), "alice", action, {}, tools={"email_send": boom})
    assert result["ok"] is False
    assert result["error"] == "smtp down"


def test_dry_run_never_calls_the_real_tool():
    calls = []

    def should_not_be_called(*a, **kw):
        calls.append(1)
        return {}

    action = {"type": "backlog_add", "params": {"project": "proj", "title_from": "subject"}}
    result = run_action(
        _acl(), "alice", action, {"subject": "x"},
        tools={"backlog_add": should_not_be_called}, dry_run=True,
    )
    assert result["dry_run"] is True
    assert calls == []


def test_notify_action_uses_injected_channels():
    sent = []

    class FakeChannel:
        def send(self, subject, markdown, text):
            sent.append((subject, text))

    action = {"type": "notify", "params": {"text_from": "subject"}}
    result = run_action(
        _acl(), "alice", action, {"subject": "Rule fired!"},
        tools={"_channels": [FakeChannel()]},
    )
    assert result["ok"] is True
    assert sent == [("Memaix — automation", "Rule fired!")]


def test_notify_action_one_broken_channel_does_not_block_others():
    sent = []

    class Good:
        def send(self, s, m, t):
            sent.append(1)

    class Bad:
        def send(self, s, m, t):
            raise RuntimeError("down")

    action = {"type": "notify", "params": {"text": "hi"}}
    result = run_action(_acl(), "alice", action, {}, tools={"_channels": [Bad(), Good()]})
    assert result["ok"] is False
    assert len(result["errors"]) == 1
    assert sent == [1]
