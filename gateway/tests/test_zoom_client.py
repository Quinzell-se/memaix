# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for booking.zoom_client — memaix-src card 85854d2c.

HTTP is mocked by monkeypatching requests.post/patch/delete with a fake
response object, same convention as test_mail_microsoft_server.py and
test_gemma_agent.py's call_ollama tests."""

from __future__ import annotations

import pytest

from memaix_gateway.booking.zoom_client import (
    ZoomAPIError,
    ZoomAuthError,
    create_zoom_meeting,
    delete_zoom_meeting,
    get_access_token,
    update_zoom_meeting,
)


class _FakeResp:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.text = text

    def json(self):
        return self._json


# --- get_access_token -----------------------------------------------------


def test_get_access_token_success(monkeypatch):
    captured = {}

    def fake_post(url, params=None, auth=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        captured["auth"] = auth
        return _FakeResp(200, {"access_token": "tok-123"})

    monkeypatch.setattr("requests.post", fake_post)

    token = get_access_token("acct1", "client1", "secret1")

    assert token == "tok-123"
    assert captured["params"] == {"grant_type": "account_credentials", "account_id": "acct1"}
    assert captured["auth"] == ("client1", "secret1")


def test_get_access_token_auth_failure_raises(monkeypatch):
    monkeypatch.setattr("requests.post", lambda *a, **kw: _FakeResp(401, text="invalid_client"))

    with pytest.raises(ZoomAuthError, match="401"):
        get_access_token("acct1", "client1", "bad-secret")


def test_get_access_token_missing_access_token_raises(monkeypatch):
    monkeypatch.setattr("requests.post", lambda *a, **kw: _FakeResp(200, {}))

    with pytest.raises(ZoomAuthError, match="no access_token"):
        get_access_token("acct1", "client1", "secret1")


# --- create_zoom_meeting ---------------------------------------------------


def test_create_zoom_meeting_success(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return _FakeResp(201, {"id": "111", "join_url": "https://zoom.us/j/111"})

    monkeypatch.setattr("requests.post", fake_post)

    meeting = create_zoom_meeting("tok-123", topic="Sync", start_time="2026-01-01T10:00:00Z", duration_min=30)

    assert meeting == {"id": "111", "join_url": "https://zoom.us/j/111"}
    assert captured["headers"] == {"Authorization": "Bearer tok-123"}
    assert captured["json"]["topic"] == "Sync"
    assert captured["json"]["duration"] == 30
    assert captured["url"].endswith("/users/me/meetings")


def test_create_zoom_meeting_api_error_raises(monkeypatch):
    monkeypatch.setattr("requests.post", lambda *a, **kw: _FakeResp(400, text="bad request"))

    with pytest.raises(ZoomAPIError, match="400"):
        create_zoom_meeting("tok-123", topic="Sync", start_time="2026-01-01T10:00:00Z", duration_min=30)


# --- update_zoom_meeting ---------------------------------------------------


def test_update_zoom_meeting_success(monkeypatch):
    captured = {}

    def fake_patch(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return _FakeResp(204)

    monkeypatch.setattr("requests.patch", fake_patch)

    update_zoom_meeting("tok-123", "111", start_time="2026-01-01T11:00:00Z", duration_min=45)

    assert captured["url"].endswith("/meetings/111")
    assert captured["json"] == {"start_time": "2026-01-01T11:00:00Z", "duration": 45}


def test_update_zoom_meeting_failure_raises(monkeypatch):
    monkeypatch.setattr("requests.patch", lambda *a, **kw: _FakeResp(404, text="not found"))

    with pytest.raises(ZoomAPIError, match="404"):
        update_zoom_meeting("tok-123", "111", start_time="2026-01-01T11:00:00Z", duration_min=45)


# --- delete_zoom_meeting ---------------------------------------------------


def test_delete_zoom_meeting_success(monkeypatch):
    captured = {}

    def fake_delete(url, headers=None, timeout=None):
        captured["url"] = url
        return _FakeResp(204)

    monkeypatch.setattr("requests.delete", fake_delete)

    delete_zoom_meeting("tok-123", "111")

    assert captured["url"].endswith("/meetings/111")


def test_delete_zoom_meeting_tolerates_404_already_gone(monkeypatch):
    monkeypatch.setattr("requests.delete", lambda *a, **kw: _FakeResp(404, text="not found"))

    delete_zoom_meeting("tok-123", "111")  # must not raise


def test_delete_zoom_meeting_other_failure_raises(monkeypatch):
    monkeypatch.setattr("requests.delete", lambda *a, **kw: _FakeResp(500, text="server error"))

    with pytest.raises(ZoomAPIError, match="500"):
        delete_zoom_meeting("tok-123", "111")
