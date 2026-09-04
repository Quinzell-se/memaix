# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for connectors.calendar_sources.SourceSelectionStore — memaix-src
card 324dd801."""

from __future__ import annotations

import pytest

from memaix_gateway.acl import Acl
from memaix_gateway.connectors.calendar_sources import SourceSelectionStore
from memaix_gateway.safety.net import BlockedURLError


def _acl(tmp_path):
    return Acl(
        users={"alice": {"grants": {"acme": "owner"}}},
        projects={"acme": {"vault": str(tmp_path)}},
    )


def test_list_empty_store_returns_empty_disabled_and_links(tmp_path):
    store = SourceSelectionStore(_acl(tmp_path), "acme", "alice")
    assert store.list() == {"disabled": [], "public_links": []}


def test_set_enabled_false_adds_label_to_disabled(tmp_path):
    store = SourceSelectionStore(_acl(tmp_path), "acme", "alice")
    store.set_enabled("google:alice@gmail.com", False)
    assert store.list()["disabled"] == ["google:alice@gmail.com"]


def test_set_enabled_true_removes_label_from_disabled(tmp_path):
    store = SourceSelectionStore(_acl(tmp_path), "acme", "alice")
    store.set_enabled("google:alice@gmail.com", False)
    store.set_enabled("google:alice@gmail.com", True)
    assert store.list()["disabled"] == []


def test_set_enabled_is_idempotent_both_directions(tmp_path):
    store = SourceSelectionStore(_acl(tmp_path), "acme", "alice")
    store.set_enabled("x", False)
    store.set_enabled("x", False)
    assert store.list()["disabled"] == ["x"]
    store.set_enabled("x", True)
    store.set_enabled("x", True)
    assert store.list()["disabled"] == []


def test_add_public_link_persists_with_generated_id(tmp_path):
    acl = _acl(tmp_path)
    entry = SourceSelectionStore(acl, "acme", "alice").add_public_link("https://x.example/cal.ics", "Fotboll")
    assert entry["id"].startswith("pl_")
    assert entry["label"] == "Fotboll"
    stored = SourceSelectionStore(acl, "acme", "alice").list()["public_links"]
    assert stored == [entry]


def test_add_public_link_dedupes_by_normalized_url_returns_existing(tmp_path):
    acl = _acl(tmp_path)
    store = SourceSelectionStore(acl, "acme", "alice")
    first = store.add_public_link("https://x.example/cal.ics")
    second = store.add_public_link("https://X.example/cal.ics/")
    assert first == second
    assert len(store.list()["public_links"]) == 1


def test_add_public_link_rejects_internal_url(tmp_path):
    store = SourceSelectionStore(_acl(tmp_path), "acme", "alice")
    with pytest.raises(BlockedURLError):
        store.add_public_link("http://169.254.169.254/latest/meta-data/")


def test_add_public_link_treats_webcal_as_https_for_dedupe(tmp_path):
    acl = _acl(tmp_path)
    store = SourceSelectionStore(acl, "acme", "alice")
    first = store.add_public_link("webcal://x.example/cal.ics")
    second = store.add_public_link("https://x.example/cal.ics")
    assert first == second


def test_remove_public_link_valid_id_returns_true(tmp_path):
    acl = _acl(tmp_path)
    store = SourceSelectionStore(acl, "acme", "alice")
    entry = store.add_public_link("https://x.example/cal.ics")
    assert store.remove_public_link(entry["id"]) is True
    assert store.list()["public_links"] == []


def test_remove_public_link_unknown_id_returns_false(tmp_path):
    store = SourceSelectionStore(_acl(tmp_path), "acme", "alice")
    assert store.remove_public_link("pl_nope") is False


def test_disabled_set_persists_across_store_instances(tmp_path):
    acl = _acl(tmp_path)
    SourceSelectionStore(acl, "acme", "alice").set_enabled("caldav:acme", False)
    assert SourceSelectionStore(acl, "acme", "alice").list()["disabled"] == ["caldav:acme"]
