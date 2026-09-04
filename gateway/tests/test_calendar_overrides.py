# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for connectors.calendar_overrides — memaix-src card 4daa20e2."""

from __future__ import annotations

from datetime import datetime, timezone

from memaix_gateway.acl import Acl
from memaix_gateway.connectors.aggregate import BusyInterval
from memaix_gateway.connectors.calendar_overrides import OverrideStore


def _dt(h: int) -> datetime:
    return datetime(2026, 1, 5, h, tzinfo=timezone.utc)


def _acl(tmp_path):
    return Acl(
        users={"alice": {"grants": {"acme": "owner"}}},
        projects={"acme": {"vault": str(tmp_path)}},
    )


def test_list_empty_store_returns_empty_lists(tmp_path):
    store = OverrideStore(_acl(tmp_path), "acme", "alice")
    assert store.list() == {"busy": [], "free": []}


def test_add_busy_persists_across_instances(tmp_path):
    acl = _acl(tmp_path)
    OverrideStore(acl, "acme", "alice").add_busy(_dt(9), _dt(10), note="blocked")
    data = OverrideStore(acl, "acme", "alice").list()
    assert data["busy"] == [{"start": _dt(9).isoformat(), "end": _dt(10).isoformat(), "note": "blocked"}]


def test_add_free_persists(tmp_path):
    acl = _acl(tmp_path)
    OverrideStore(acl, "acme", "alice").add_free(_dt(9), _dt(10))
    data = OverrideStore(acl, "acme", "alice").list()
    assert data["free"] == [{"start": _dt(9).isoformat(), "end": _dt(10).isoformat(), "note": ""}]


def test_remove_valid_index_returns_true_and_removes(tmp_path):
    acl = _acl(tmp_path)
    store = OverrideStore(acl, "acme", "alice")
    store.add_busy(_dt(9), _dt(10))
    store.add_busy(_dt(11), _dt(12))
    assert store.remove("busy", 0) is True
    assert store.list()["busy"] == [{"start": _dt(11).isoformat(), "end": _dt(12).isoformat(), "note": ""}]


def test_remove_out_of_range_index_returns_false(tmp_path):
    store = OverrideStore(_acl(tmp_path), "acme", "alice")
    assert store.remove("busy", 0) is False


def test_apply_with_no_overrides_returns_input_unchanged(tmp_path):
    store = OverrideStore(_acl(tmp_path), "acme", "alice")
    busy = [BusyInterval(_dt(9), _dt(10), "src")]
    assert store.apply(busy) == busy


def test_apply_unions_busy_override_into_result(tmp_path):
    acl = _acl(tmp_path)
    store = OverrideStore(acl, "acme", "alice")
    store.add_busy(_dt(14), _dt(15), note="blocked")
    result = store.apply([BusyInterval(_dt(9), _dt(10), "src")])
    assert result == [BusyInterval(_dt(9), _dt(10), "src"), BusyInterval(_dt(14), _dt(15), "override:busy")]


def test_apply_busy_override_merges_with_overlapping_source_interval(tmp_path):
    acl = _acl(tmp_path)
    store = OverrideStore(acl, "acme", "alice")
    store.add_busy(_dt(9), _dt(11))
    result = store.apply([BusyInterval(_dt(10), _dt(12), "src")])
    assert result == [BusyInterval(_dt(9), _dt(12), "override:busy")]


def test_apply_free_override_removes_fully_covered_busy_block(tmp_path):
    acl = _acl(tmp_path)
    store = OverrideStore(acl, "acme", "alice")
    store.add_free(_dt(9), _dt(10))
    result = store.apply([BusyInterval(_dt(9), _dt(10), "src")])
    assert result == []


def test_apply_free_override_splits_busy_block_in_two(tmp_path):
    acl = _acl(tmp_path)
    store = OverrideStore(acl, "acme", "alice")
    store.add_free(_dt(10), _dt(11))
    result = store.apply([BusyInterval(_dt(9), _dt(12), "src")])
    assert result == [BusyInterval(_dt(9), _dt(10), "src"), BusyInterval(_dt(11), _dt(12), "src")]


def test_apply_free_override_disjoint_from_busy_has_no_effect(tmp_path):
    acl = _acl(tmp_path)
    store = OverrideStore(acl, "acme", "alice")
    store.add_free(_dt(14), _dt(15))
    busy = [BusyInterval(_dt(9), _dt(10), "src")]
    assert store.apply(busy) == busy
