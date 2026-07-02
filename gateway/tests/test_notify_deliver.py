# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for notify.deliver.deliver."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from memaix_gateway.acl import Acl
from memaix_gateway.notify.deliver import deliver
from memaix_gateway.notify.store import NotifyStore

NOW = datetime(2026, 1, 15, 7, 0, tzinfo=timezone.utc)


@pytest.fixture()
def store(tmp_path):
    return NotifyStore.for_path(tmp_path / "notify.db")


@pytest.fixture()
def acl():
    return Acl(users={"alice": {"grants": {"proj": "owner"}}}, projects={"proj": {"vault": "/v"}})


class _RecordingChannel:
    def __init__(self):
        self.sent = []

    def send(self, subject, markdown, text):
        self.sent.append((subject, markdown, text))


class _FailingChannel:
    def send(self, subject, markdown, text):
        raise RuntimeError("channel down")


def _prefs(**overrides):
    base = {"enabled": True, "timezone": "UTC", "brief_time": "07:00", "channels": [], "projects": ["proj"]}
    base.update(overrides)
    return base


def test_deliver_sends_once_and_is_idempotent(store, acl):
    ch = _RecordingChannel()
    result1 = deliver(store, acl, None, "alice", _prefs(), now=NOW, _channels=[ch])
    assert result1["ok"] is True
    assert len(ch.sent) == 1

    result2 = deliver(store, acl, None, "alice", _prefs(), now=NOW, _channels=[ch])
    assert result2 == {"skipped": "duplicate"}
    assert len(ch.sent) == 1  # not sent twice


def test_deliver_force_bypasses_idempotency(store, acl):
    ch = _RecordingChannel()
    deliver(store, acl, None, "alice", _prefs(), now=NOW, _channels=[ch])
    result = deliver(store, acl, None, "alice", _prefs(), now=NOW, force=True, _channels=[ch])
    assert result["ok"] is True
    assert len(ch.sent) == 2


def test_deliver_respects_quiet_hours(store, acl):
    ch = _RecordingChannel()
    prefs = _prefs(quiet_start="06:00", quiet_end="09:00")
    result = deliver(store, acl, None, "alice", prefs, now=NOW, _channels=[ch])  # NOW is 07:00
    assert result == {"skipped": "quiet_hours"}
    assert ch.sent == []


def test_deliver_force_bypasses_quiet_hours(store, acl):
    ch = _RecordingChannel()
    prefs = _prefs(quiet_start="06:00", quiet_end="09:00")
    result = deliver(store, acl, None, "alice", prefs, now=NOW, force=True, _channels=[ch])
    assert result["ok"] is True
    assert len(ch.sent) == 1


def test_deliver_one_broken_channel_does_not_stop_others(store, acl):
    good = _RecordingChannel()
    bad = _FailingChannel()
    result = deliver(store, acl, None, "alice", _prefs(), now=NOW, _channels=[bad, good])
    assert result["delivered"] == 1
    assert len(result["errors"]) == 1
    assert len(good.sent) == 1


def test_deliver_skips_when_empty_and_send_when_empty_false(store, acl):
    cfg = {"memaix": {"brief": {"send_when_empty": False}}}
    ch = _RecordingChannel()
    result = deliver(store, acl, cfg, "alice", _prefs(), now=NOW, _channels=[ch])
    assert result == {"skipped": "empty"}
    assert ch.sent == []
