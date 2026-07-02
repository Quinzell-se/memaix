# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for rules.store.RulesStore."""

from __future__ import annotations

import pytest

from memaix_gateway.rules.store import RulesStore


@pytest.fixture()
def store(tmp_path):
    return RulesStore.for_path(tmp_path / "rules.db")


def test_add_and_get_rule(store):
    rule = store.add_rule(
        "alice", "proj", "New client mail", {"type": "mail", "from_contains": "@client.com"},
        [{"type": "backlog_add", "params": {"project": "proj", "title_from": "subject"}}],
    )
    assert rule["enabled"] is True
    fetched = store.get_rule(rule["id"])
    assert fetched == rule


def test_get_missing_rule_returns_none(store):
    assert store.get_rule("nope") is None


def test_list_rules_filters_by_project_and_enabled(store):
    r1 = store.add_rule("alice", "proj-a", "r1", {"type": "mail"}, [])
    store.add_rule("alice", "proj-b", "r2", {"type": "mail"}, [])
    store.set_enabled(r1["id"], False)

    assert len(store.list_rules(["proj-a"])) == 1
    assert len(store.list_rules(["proj-a", "proj-b"])) == 2
    assert len(store.list_rules(["proj-a"], enabled_only=True)) == 0
    assert len(store.list_rules(enabled_only=True)) == 1


def test_set_enabled_toggles(store):
    rule = store.add_rule("alice", "proj", "r", {"type": "mail"}, [])
    assert store.set_enabled(rule["id"], False) is True
    assert store.get_rule(rule["id"])["enabled"] is False
    assert store.set_enabled(rule["id"], True) is True
    assert store.get_rule(rule["id"])["enabled"] is True


def test_set_enabled_unknown_rule_returns_false(store):
    assert store.set_enabled("nope", False) is False


def test_delete_rule(store):
    rule = store.add_rule("alice", "proj", "r", {"type": "mail"}, [])
    assert store.delete_rule(rule["id"]) is True
    assert store.get_rule(rule["id"]) is None
    assert store.delete_rule(rule["id"]) is False


def test_try_reserve_idempotent(store):
    rule = store.add_rule("alice", "proj", "r", {"type": "mail"}, [])
    assert store.try_reserve(rule["id"], "event-1") is True
    assert store.try_reserve(rule["id"], "event-1") is False  # already reserved
    assert store.try_reserve(rule["id"], "event-2") is True  # different event, OK


def test_record_run_detail_and_list_runs(store):
    rule = store.add_rule("alice", "proj", "r", {"type": "mail"}, [])
    store.try_reserve(rule["id"], "event-1")
    store.record_run_detail(rule["id"], "event-1", False, "boom")
    runs = store.list_runs(rule["id"])
    assert len(runs) == 1
    assert runs[0]["ok"] == 0
    assert runs[0]["detail"] == "boom"


def test_standing_instructions_set_and_get(store):
    assert store.get_standing("alice") is None
    store.set_standing("alice", "Always answer in Swedish.")
    assert store.get_standing("alice") == "Always answer in Swedish."
    store.set_standing("alice", "Updated instruction.")
    assert store.get_standing("alice") == "Updated instruction."
