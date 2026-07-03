# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the web-UI app shell routes (FEATURE-WEB-UI-FOUNDATION.md).

Auth is bypassed by monkeypatching _require_user (same pattern as the board
tests) — cookie auth itself is exercised by the board test suite; these tests
cover pages, static serving, the 301 board redirect and /app/api/me.
"""

from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from memaix_gateway.acl import Acl
from memaix_gateway.web import routes as web_routes_mod


@pytest.fixture()
def rig(tmp_path, monkeypatch):
    acl = Acl(
        users={
            "alice": {"grants": {"acme": "owner", "beta": "reader"}},
            "root": {"admin": True},
        },
        projects={"acme": {"vault": str(tmp_path / "a")}, "beta": {"vault": str(tmp_path / "b")}},
    )
    monkeypatch.setattr(web_routes_mod, "_get_acl", lambda: acl)
    current = {"user": "alice"}
    monkeypatch.setattr(web_routes_mod, "_require_user", lambda request: current["user"])
    monkeypatch.delenv("MEMAIX_TOKEN_DB", raising=False)
    monkeypatch.setenv("MEMAIX_OUTBOX_DB", str(tmp_path / "outbox.db"))

    app = Starlette(routes=web_routes_mod.web_routes)
    return TestClient(app), current


def test_board_redirects_301_preserving_query(rig):
    client, _ = rig
    resp = client.get("/board?project=acme&sprint=active", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/board?project=acme&sprint=active"

    resp = client.get("/board", follow_redirects=False)
    assert resp.headers["Location"] == "/app/board"


def test_app_index_serves_dark_shell(rig):
    client, _ = rig
    resp = client.get("/app")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "sidebar" in resp.text
    assert "window.I18N=" in resp.text  # i18n injected


def test_app_known_page_and_404(rig):
    client, _ = rig
    assert client.get("/app/board").status_code == 200
    assert client.get("/app/nonexistent").status_code == 404


def test_static_css_has_design_tokens(rig):
    client, _ = rig
    resp = client.get("/app/static/app.css")
    assert resp.status_code == 200
    assert "text/css" in resp.headers["content-type"]
    assert "--bg:           #0f1117;" in resp.text
    assert "--sidebar-w:    220px;" in resp.text


def test_static_path_traversal_blocked(rig):
    client, _ = rig
    # Encoded traversal must not escape the static dir.
    resp = client.get("/app/static/..%2f..%2froutes.py")
    assert resp.status_code == 404
    resp = client.get("/app/static/../routes.py")
    assert resp.status_code == 404


def test_api_me_shape(rig):
    client, _ = rig
    resp = client.get("/app/api/me")
    assert resp.status_code == 200
    me = resp.json()
    assert me["user"] == "alice"
    assert me["is_admin"] is False
    assert me["projects"] == ["acme", "beta"]
    assert me["role_map"] == {"acme": "owner", "beta": "reader"}
    assert me["needs_relink"] == []
    assert me["pending_outbox"] == 0
    assert me["onboarding_missing"] is False


def test_api_me_admin_sees_all_projects(rig):
    client, current = rig
    current["user"] = "root"
    me = client.get("/app/api/me").json()
    assert me["is_admin"] is True
    assert me["projects"] == ["acme", "beta"]
    assert me["role_map"] == {"acme": "admin", "beta": "admin"}


def test_api_me_401_when_unauthenticated(rig, monkeypatch):
    client, _ = rig
    monkeypatch.setattr(web_routes_mod, "_require_user", lambda request: None)
    resp = client.get("/app/api/me")
    assert resp.status_code == 401


def test_pages_401_do_not_apply(rig, monkeypatch):
    # Pages themselves render without auth (client JS redirects on 401 from
    # the API) — mirrors the board.html pattern with its inline login card.
    client, _ = rig
    monkeypatch.setattr(web_routes_mod, "_require_user", lambda request: None)
    assert client.get("/app").status_code == 200


def test_board_frame_serves_board_html_with_dark_override(rig):
    client, _ = rig
    resp = client.get("/app/board/frame")
    assert resp.status_code == 200
    assert "--bg:#0f1117" in resp.text  # dark override injected
