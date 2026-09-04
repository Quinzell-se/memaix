# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the booking-link slug registry — memaix-src card 2bef1062."""

from __future__ import annotations

import json

import pytest

from memaix_gateway import config
from memaix_gateway.booking.links import get_link


@pytest.fixture(autouse=True)
def _config_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    return tmp_path


def test_unknown_slug_returns_none():
    assert get_link("nope") is None


def test_empty_slug_returns_none():
    assert get_link("") is None


def test_path_traversal_slug_returns_none():
    assert get_link("../secrets") is None
    assert get_link("a/b") is None


def test_valid_link_is_returned(_config_dir):
    d = _config_dir / "booking_links"
    d.mkdir()
    (d / "alice-30.json").write_text(json.dumps({"project": "proj", "user": "alice", "duration_min": 30}))
    link = get_link("alice-30")
    assert link == {"project": "proj", "user": "alice", "duration_min": 30}


def test_malformed_json_returns_none(_config_dir):
    d = _config_dir / "booking_links"
    d.mkdir()
    (d / "broken.json").write_text("{not json")
    assert get_link("broken") is None


def test_missing_required_fields_returns_none(_config_dir):
    d = _config_dir / "booking_links"
    d.mkdir()
    (d / "incomplete.json").write_text(json.dumps({"project": "proj"}))
    assert get_link("incomplete") is None
