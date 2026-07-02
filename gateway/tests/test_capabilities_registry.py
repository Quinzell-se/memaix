# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for capabilities.registry — the discoverability source of truth."""

from __future__ import annotations

import pytest

from memaix_gateway.acl import Acl
from memaix_gateway.capabilities import catalog
from memaix_gateway.capabilities.registry import (
    Capability,
    all_capabilities,
    available_for,
    clear_registry,
    group_by_area,
    register,
)


@pytest.fixture(autouse=True)
def _isolated_registry():
    """Each test gets a clean registry so tests don't leak into each other."""
    clear_registry()
    yield
    # Restore the real catalog rather than leave the global registry empty —
    # other test modules (and server.py itself) assume it reflects reality.
    clear_registry()
    catalog.register_defaults()


@pytest.fixture()
def acl():
    return Acl(
        users={
            "alice": {"grants": {"acme": "owner"}},
            "bob": {"grants": {"acme": "reader"}},
        },
        projects={"acme": {"vault": "/srv/vaults/acme", "mailbox": {"host": "x"}}},
    )


def test_register_and_all_capabilities():
    cap = Capability(
        key="memory.remember", area="memory", title_key="t", summary_key="s",
        tools=("memory_write",), example_prompts_key="e",
        needs_role="collaborator", needs_resource="vault",
    )
    register(cap)
    assert all_capabilities() == [cap]


def test_register_is_idempotent_by_key():
    cap = Capability(
        key="memory.remember", area="memory", title_key="t", summary_key="s",
        tools=("memory_write",), example_prompts_key="e",
    )
    register(cap, cap)
    assert len(all_capabilities()) == 1


def test_available_for_filters_by_role(acl):
    register(
        Capability(
            key="backlog.decide", area="backlog", title_key="t", summary_key="s",
            tools=("backlog_set_status",), example_prompts_key="e",
            needs_role="owner", needs_resource="vault",
        )
    )
    available, locked = available_for(acl, "alice")
    assert len(available) == 1
    available, locked = available_for(acl, "bob")
    assert available == []
    assert locked[0]["reason"] == "no_role"


def test_available_for_locks_on_missing_resource(acl):
    register(
        Capability(
            key="mail.triage", area="mail", title_key="t", summary_key="s",
            tools=("email_list",), example_prompts_key="e",
            needs_role="reader", needs_resource="calendar",  # acme has no calendar
        )
    )
    available, locked = available_for(acl, "alice")
    assert available == []
    assert locked[0]["reason"] == "no_calendar"


def test_available_for_locks_on_missing_account(acl):
    register(
        Capability(
            key="calendar.sync", area="calendar", title_key="t", summary_key="s",
            tools=("calendar_list",), example_prompts_key="e",
            needs_role="reader", needs_account="google",
        )
    )
    available, locked = available_for(acl, "alice", accounts=[])
    assert available == []
    assert locked[0]["reason"] == "link_google"

    available, _ = available_for(
        acl, "alice", accounts=[{"provider": "google", "account": "a@x.com"}]
    )
    assert len(available) == 1


def test_available_for_resource_present_unlocks(acl):
    register(
        Capability(
            key="mail.triage", area="mail", title_key="t", summary_key="s",
            tools=("email_list",), example_prompts_key="e",
            needs_role="reader", needs_resource="mailbox",
        )
    )
    available, locked = available_for(acl, "alice")
    assert len(available) == 1
    assert locked == []


def test_unknown_user_has_nothing_available(acl):
    register(
        Capability(
            key="memory.recall", area="memory", title_key="t", summary_key="s",
            tools=("memory_read",), example_prompts_key="e", needs_role="reader",
        )
    )
    available, locked = available_for(acl, "ghost")
    assert available == []
    assert locked[0]["reason"] == "no_role"


def test_group_by_area_preserves_order():
    register(
        Capability(key="a1", area="mail", title_key="t", summary_key="s", tools=(), example_prompts_key="e"),
        Capability(key="a2", area="memory", title_key="t", summary_key="s", tools=(), example_prompts_key="e"),
        Capability(key="a3", area="mail", title_key="t", summary_key="s", tools=(), example_prompts_key="e"),
    )
    grouped = group_by_area(all_capabilities())
    assert list(grouped.keys()) == ["mail", "memory"]
    assert [c.key for c in grouped["mail"]] == ["a1", "a3"]
