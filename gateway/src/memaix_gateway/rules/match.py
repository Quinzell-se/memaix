# SPDX-License-Identifier: AGPL-3.0-or-later
"""Trigger matching and the conditions mini-DSL.

See docs/FEATURE-AUTOMATION-RULES.md §4/§6. Pure functions — no I/O, so the
engine can be tested by feeding it synthetic events without a live trigger
source (mail poller, webhook, scheduler).
"""

from __future__ import annotations

import re


def trigger_matches(trigger: dict, event: dict) -> bool:
    """Does *trigger* fire for *event*?  event = {"type", "project", "id", "payload"}."""
    if trigger.get("type") != event.get("type"):
        return False

    ttype = trigger["type"]
    payload = event.get("payload", {}) or {}

    if ttype == "mail":
        if trigger.get("project") and trigger["project"] != event.get("project"):
            return False
        from_contains = trigger.get("from_contains", "")
        if from_contains and from_contains.lower() not in (payload.get("from") or "").lower():
            return False
        subject_contains = trigger.get("subject_contains", "")
        if subject_contains and subject_contains.lower() not in (payload.get("subject") or "").lower():
            return False
        return True

    if ttype == "internal":
        if trigger.get("event") != payload.get("event"):
            return False
        expected_to = trigger.get("to")
        if expected_to is not None and payload.get("to") != expected_to:
            return False
        return True

    if ttype == "webhook":
        return bool(trigger.get("token")) and trigger["token"] == payload.get("token")

    if ttype == "schedule":
        # Time-window filtering happens before the event reaches evaluate();
        # here we only confirm this is a schedule-shaped trigger.
        return bool(trigger.get("cron"))

    return False


def _op_contains(field_value, expected) -> bool:
    return str(expected).lower() in str(field_value).lower()


def _op_equals(field_value, expected) -> bool:
    return field_value == expected


def _op_matches(field_value, expected) -> bool:
    return re.search(str(expected), str(field_value)) is not None


_OPS = {"contains": _op_contains, "equals": _op_equals, "matches": _op_matches}


def conditions_pass(conditions: list[dict], payload: dict) -> bool:
    """All conditions must pass (AND). An unknown op fails closed."""
    payload = payload or {}
    for cond in conditions or []:
        op_fn = _OPS.get(cond.get("op") or "")
        if op_fn is None:
            return False
        if not op_fn(payload.get(cond.get("field"), ""), cond.get("value")):
            return False
    return True
