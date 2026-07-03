# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for outbox.policy.action_mode."""

from __future__ import annotations

from memaix_gateway.acl import Acl
from memaix_gateway.outbox.policy import action_mode


def _acl(project_extra: dict | None = None) -> Acl:
    return Acl(
        users={"alice": {"grants": {"proj": "owner"}}},
        projects={"proj": {"vault": "/v", **(project_extra or {})}},
    )


def test_default_mode_is_auto_when_unconfigured():
    acl = _acl()
    assert action_mode(None, acl, "proj", "email_send", {"to": "x@y.com"}) == "auto"


def test_project_review_mode_overrides_default():
    acl = _acl({"outbox": "review"})
    assert action_mode(None, acl, "proj", "email_send", {"to": "x@y.com"}) == "review"


def test_global_default_mode_from_config():
    acl = _acl()
    cfg = {"memaix": {"outbox": {"default_mode": "review"}}}
    assert action_mode(cfg, acl, "proj", "email_send", {"to": "x@y.com"}) == "review"


def test_project_mode_wins_over_global_default():
    acl = _acl({"outbox": "auto"})
    cfg = {"memaix": {"outbox": {"default_mode": "review"}}}
    assert action_mode(cfg, acl, "proj", "email_send", {"to": "x@y.com"}) == "auto"


def test_allowlist_forces_review_for_unlisted_recipient():
    acl = _acl({"allowlist": ["@trusted.example"]})
    assert action_mode(None, acl, "proj", "email_send", {"to": "x@evil.example"}) == "review"


def test_allowlist_allows_listed_recipient():
    acl = _acl({"allowlist": ["@trusted.example"]})
    assert action_mode(None, acl, "proj", "email_send", {"to": "x@trusted.example"}) == "auto"


def test_allowlist_exact_address_match():
    acl = _acl({"allowlist": ["specific@x.com"]})
    assert action_mode(None, acl, "proj", "email_send", {"to": "specific@x.com"}) == "auto"
    assert action_mode(None, acl, "proj", "email_send", {"to": "other@x.com"}) == "review"


def test_no_allowlist_configured_means_no_restriction():
    acl = _acl()
    assert action_mode(None, acl, "proj", "email_send", {"to": "anyone@anywhere.com"}) == "auto"


def test_calendar_attendees_checked_against_allowlist():
    acl = _acl({"allowlist": ["@trusted.example"]})
    args = {"attendees": ["a@evil.example"]}
    assert action_mode(None, acl, "proj", "calendar_create", args) == "review"
