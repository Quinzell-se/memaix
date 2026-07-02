# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for rules.match — trigger matching and the conditions DSL."""

from __future__ import annotations

from memaix_gateway.rules.match import conditions_pass, trigger_matches


def test_mail_trigger_matches_on_from_contains():
    trigger = {"type": "mail", "from_contains": "@client.com"}
    event = {"type": "mail", "project": "proj", "payload": {"from": "x@client.com", "subject": "hi"}}
    assert trigger_matches(trigger, event) is True


def test_mail_trigger_rejects_wrong_sender():
    trigger = {"type": "mail", "from_contains": "@client.com"}
    event = {"type": "mail", "project": "proj", "payload": {"from": "x@other.com"}}
    assert trigger_matches(trigger, event) is False


def test_mail_trigger_project_scoped():
    trigger = {"type": "mail", "project": "acme", "from_contains": "@client.com"}
    event = {"type": "mail", "project": "other", "payload": {"from": "x@client.com"}}
    assert trigger_matches(trigger, event) is False


def test_mail_trigger_subject_contains():
    trigger = {"type": "mail", "subject_contains": "invoice"}
    assert trigger_matches(trigger, {"type": "mail", "payload": {"subject": "Your Invoice #42"}}) is True
    assert trigger_matches(trigger, {"type": "mail", "payload": {"subject": "Meeting notes"}}) is False


def test_internal_trigger_matches_event_and_to_value():
    trigger = {"type": "internal", "event": "backlog.status", "to": "done"}
    event = {"type": "internal", "payload": {"event": "backlog.status", "to": "done", "from": "in-dev"}}
    assert trigger_matches(trigger, event) is True

    event_wrong_to = {"type": "internal", "payload": {"event": "backlog.status", "to": "rejected"}}
    assert trigger_matches(trigger, event_wrong_to) is False


def test_internal_trigger_without_to_matches_any_transition():
    trigger = {"type": "internal", "event": "backlog.status"}
    event = {"type": "internal", "payload": {"event": "backlog.status", "to": "anything"}}
    assert trigger_matches(trigger, event) is True


def test_webhook_trigger_matches_token():
    trigger = {"type": "webhook", "token": "secret123"}
    assert trigger_matches(trigger, {"type": "webhook", "payload": {"token": "secret123"}}) is True
    assert trigger_matches(trigger, {"type": "webhook", "payload": {"token": "wrong"}}) is False


def test_webhook_trigger_rejects_missing_or_nonstring_token():
    # Constant-time compare requires a real string on both sides; a missing
    # trigger token or a non-string provided token must fail closed.
    assert trigger_matches({"type": "webhook", "token": ""}, {"type": "webhook", "payload": {"token": "x"}}) is False
    assert trigger_matches({"type": "webhook"}, {"type": "webhook", "payload": {"token": "x"}}) is False
    assert trigger_matches({"type": "webhook", "token": "s"}, {"type": "webhook", "payload": {}}) is False
    assert trigger_matches({"type": "webhook", "token": "s"}, {"type": "webhook", "payload": {"token": 123}}) is False


def test_trigger_type_mismatch_never_matches():
    trigger = {"type": "mail", "from_contains": "x"}
    assert trigger_matches(trigger, {"type": "webhook", "payload": {}}) is False


def test_conditions_pass_all_and():
    conditions = [
        {"field": "subject", "op": "contains", "value": "invoice"},
        {"field": "amount", "op": "equals", "value": 100},
    ]
    assert conditions_pass(conditions, {"subject": "Your invoice", "amount": 100}) is True
    assert conditions_pass(conditions, {"subject": "Your invoice", "amount": 200}) is False


def test_conditions_pass_matches_regex():
    conditions = [{"field": "subject", "op": "matches", "value": r"INV-\d+"}]
    assert conditions_pass(conditions, {"subject": "Reference INV-042"}) is True
    assert conditions_pass(conditions, {"subject": "no reference here"}) is False


def test_conditions_pass_unknown_op_fails_closed():
    conditions = [{"field": "x", "op": "unknown-op", "value": 1}]
    assert conditions_pass(conditions, {"x": 1}) is False


def test_conditions_pass_empty_list_is_true():
    assert conditions_pass([], {}) is True
