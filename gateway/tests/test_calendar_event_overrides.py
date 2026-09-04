# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for connectors.calendar_event_overrides — memaix-src card c7698ff3."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from memaix_gateway.acl import Acl
from memaix_gateway.connectors.aggregate import CalendarEvent
from memaix_gateway.connectors.calendar_event_overrides import EventOverrideStore


def _dt(h: int) -> datetime:
    return datetime(2026, 1, 5, h, tzinfo=timezone.utc)


def _acl(tmp_path):
    return Acl(
        users={"alice": {"grants": {"acme": "owner"}}},
        projects={"acme": {"vault": str(tmp_path)}},
    )


def _event(uid="ev1", source="caldav:acme", series_id=None, is_exception=False) -> CalendarEvent:
    return CalendarEvent(
        uid=uid, start=_dt(9), end=_dt(10), source=source,
        series_id=series_id, is_exception=is_exception,
    )


def test_list_empty_store_returns_empty_dicts(tmp_path):
    store = EventOverrideStore(_acl(tmp_path), "acme", "alice")
    assert store.list() == {"instances": {}, "series": {}}


def test_resolve_with_no_override_returns_none(tmp_path):
    store = EventOverrideStore(_acl(tmp_path), "acme", "alice")
    assert store.resolve(_event()) is None


def test_set_instance_then_resolve_returns_state(tmp_path):
    acl = _acl(tmp_path)
    store = EventOverrideStore(acl, "acme", "alice")
    store.set_instance("caldav:acme", "ev1", "free", note="konferens")
    assert store.resolve(_event()) == "free"


def test_instance_override_scoped_to_source(tmp_path):
    acl = _acl(tmp_path)
    store = EventOverrideStore(acl, "acme", "alice")
    store.set_instance("caldav:acme", "ev1", "free")
    other_source = _event(uid="ev1", source="public_ics:xyz")
    assert store.resolve(other_source) is None


def test_clear_instance_removes_override(tmp_path):
    acl = _acl(tmp_path)
    store = EventOverrideStore(acl, "acme", "alice")
    store.set_instance("caldav:acme", "ev1", "busy")
    assert store.clear_instance("caldav:acme", "ev1") is True
    assert store.resolve(_event()) is None


def test_clear_instance_missing_returns_false(tmp_path):
    store = EventOverrideStore(_acl(tmp_path), "acme", "alice")
    assert store.clear_instance("caldav:acme", "nope") is False


def test_set_series_applies_to_normal_occurrence(tmp_path):
    acl = _acl(tmp_path)
    store = EventOverrideStore(acl, "acme", "alice")
    store.set_series("caldav:acme", "series-1", "busy")
    occurrence = _event(uid="ev2", series_id="series-1", is_exception=False)
    assert store.resolve(occurrence) == "busy"


def test_series_override_does_not_apply_to_exception_instance(tmp_path):
    """Card decision (2026-09-04 14:35 UTC): an instance that broke out of
    its series does NOT inherit the series override — must be set
    individually."""
    acl = _acl(tmp_path)
    store = EventOverrideStore(acl, "acme", "alice")
    store.set_series("caldav:acme", "series-1", "busy")
    exception = _event(uid="ev3", series_id="series-1", is_exception=True)
    assert store.resolve(exception) is None


def test_instance_override_still_works_on_exception(tmp_path):
    """An exception instance can still be overridden individually — the
    series guard only blocks *inheriting* a series-level override."""
    acl = _acl(tmp_path)
    store = EventOverrideStore(acl, "acme", "alice")
    store.set_series("caldav:acme", "series-1", "busy")
    exception = _event(uid="ev3", series_id="series-1", is_exception=True)
    store.set_instance("caldav:acme", "ev3", "free")
    assert store.resolve(exception) == "free"


def test_instance_override_wins_over_series_override(tmp_path):
    acl = _acl(tmp_path)
    store = EventOverrideStore(acl, "acme", "alice")
    store.set_series("caldav:acme", "series-1", "busy")
    occurrence = _event(uid="ev2", series_id="series-1", is_exception=False)
    store.set_instance("caldav:acme", "ev2", "free")
    assert store.resolve(occurrence) == "free"


def test_clear_series_removes_override(tmp_path):
    acl = _acl(tmp_path)
    store = EventOverrideStore(acl, "acme", "alice")
    store.set_series("caldav:acme", "series-1", "busy")
    assert store.clear_series("caldav:acme", "series-1") is True
    occurrence = _event(uid="ev2", series_id="series-1", is_exception=False)
    assert store.resolve(occurrence) is None


def test_clear_series_missing_returns_false(tmp_path):
    store = EventOverrideStore(_acl(tmp_path), "acme", "alice")
    assert store.clear_series("caldav:acme", "nope") is False


def test_set_instance_invalid_state_raises(tmp_path):
    store = EventOverrideStore(_acl(tmp_path), "acme", "alice")
    with pytest.raises(ValueError):
        store.set_instance("caldav:acme", "ev1", "maybe")


def test_set_series_invalid_state_raises(tmp_path):
    store = EventOverrideStore(_acl(tmp_path), "acme", "alice")
    with pytest.raises(ValueError):
        store.set_series("caldav:acme", "series-1", "maybe")
