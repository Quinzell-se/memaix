# SPDX-License-Identifier: AGPL-3.0-or-later
"""Setup-motorn + lokala webb-wizarden (scripts/setup_engine.py, setup_web.py).

Motorn ska skriva den AKTUELLA säkerhetsmodellen (admin: true, per-user
password_hash i både acl.yaml och .env) — regressionsskydd mot att wizarden
halkar efter koden igen. Webben testas för sitt säkerhetskontrakt:
token-krav, self-shutdown, inga hemligheter tillbaka till klienten.
"""

from __future__ import annotations

import http.client
import json
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode

import pytest
import yaml

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import setup_engine as engine  # noqa: E402
import setup_web  # noqa: E402


def _answers(**overrides):
    a = engine.defaults()
    a.update({"admin_user": "jimmy", "password": "hemligt123", "project_name": "acme"})
    a.update(overrides)
    return a


# ───────────────────────────── engine ──────────────────────────────────────


def test_write_config_current_security_model(tmp_path):
    summary = engine.write_config(_answers(), tmp_path)

    acl = yaml.safe_load((tmp_path / "config" / "acl.yaml").read_text())
    user = acl["users"]["jimmy"]
    assert user["admin"] is True, "admin-användaren måste få admin: true"
    assert ":" in user["password_hash"], "per-user hash i acl.yaml (login-appens källa)"
    assert user["grants"] == {"acme": "owner", "shared": "owner"}

    env = (tmp_path / ".env").read_text()
    assert "MEMAIX_LOGIN_PASSWORD_HASH_JIMMY=" in env, "per-user hash i .env (board-källan)"
    assert "MEMAIX_LOGIN_PASSWORD_HASH=" not in env.replace(
        "MEMAIX_LOGIN_PASSWORD_HASH_JIMMY=", ""
    ), "ingen delad hash — per-user-modellen gäller"
    assert "hemligt123" not in env, "aldrig klartextlösenord på disk"
    assert (tmp_path / ".env").stat().st_mode & 0o777 == 0o600

    assert summary["public_url"] == "http://localhost:8080"
    assert "password" not in json.dumps(summary), "sammanfattningen är hemlighetsfri"


def test_write_config_selfhost_url(tmp_path):
    a = _answers(track=engine.TRACK_SELFHOST, domain="mcp.example.se")
    engine.write_config(a, tmp_path)
    cfg = yaml.safe_load((tmp_path / "config" / "memaix.yaml").read_text())
    assert cfg["server"]["public_url"] == "https://mcp.example.se"
    assert cfg["auth"]["issuer"] == "https://mcp.example.se/"


@pytest.mark.parametrize(
    "field,value,hint",
    [
        ("admin_user", "Jimmy!", "användarnamn"),
        ("admin_user", "j", "användarnamn"),
        ("password", "kort", "8 tecken"),
        ("project_name", "Stort Projekt", "projektnamn"),
    ],
)
def test_validate_rejects(field, value, hint, tmp_path):
    errors = engine.validate(_answers(**{field: value}))
    assert errors and any(hint.lower() in e.lower() for e in errors)


def test_validate_selfhost_requires_domain():
    assert engine.validate(_answers(track=engine.TRACK_SELFHOST, domain=""))
    assert not engine.validate(_answers(track=engine.TRACK_SELFHOST, domain="mcp.x.se"))


def test_seed_vaults_idempotent(tmp_path):
    (tmp_path / "vault-template" / "PROJECT-TEMPLATE").mkdir(parents=True)
    (tmp_path / "vault-template" / "PROJECT-TEMPLATE" / "INDEX.md").write_text("x")
    first = engine.seed_vaults(tmp_path, ["acme"])
    assert set(first) == {"acme", "shared"}
    assert (tmp_path / "vaults" / "acme" / "INDEX.md").exists()
    assert engine.seed_vaults(tmp_path, ["acme"]) == [], "körs om utan att röra befintligt"


# ───────────────────────────── setup_web ───────────────────────────────────


TOKEN = "a" * 32


@pytest.fixture()
def wizard(tmp_path, monkeypatch):
    """Setup-webben mot en tom temporär repo-rot, på en ledig port."""
    monkeypatch.setattr(setup_web, "ROOT", tmp_path)
    setup_web.Handler.token = TOKEN
    setup_web.Handler.done = False
    server = ThreadingHTTPServer(("127.0.0.1", 0), setup_web.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1], tmp_path, thread
    server.shutdown()
    thread.join(timeout=5)


def _request(port, method, path, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    headers = {"Content-Type": "application/x-www-form-urlencoded"} if body else {}
    conn.request(method, path, body=body, headers=headers)
    resp = conn.getresponse()
    data = resp.read().decode()
    conn.close()
    return resp.status, data


def test_token_required(wizard):
    port, _, _ = wizard
    status, _ = _request(port, "GET", "/")
    assert status == 403
    status, _ = _request(port, "GET", f"/?token={'b' * 32}")
    assert status == 403
    status, body = _request(port, "GET", f"/?token={TOKEN}")
    assert status == 200 and "Memaix" in body


def test_apply_validates_and_never_echoes_secrets(wizard):
    port, _, _ = wizard
    fields = urlencode({
        "track": "1", "admin_user": "jimmy",
        "password": "hemligt123", "password2": "annat-lösen",
    })
    status, body = _request(port, "POST", f"/apply?token={TOKEN}", fields)
    assert status == 200 and "matchar inte" in body
    assert "hemligt123" not in body and "annat-lösen" not in body


def test_done_flag_closes_surface(wizard):
    port, _, _ = wizard
    setup_web.Handler.done = True
    status, _ = _request(port, "GET", f"/?token={TOKEN}")
    assert status == 410


def test_apply_writes_config_and_shuts_down(wizard):
    port, root, thread = wizard
    fields = urlencode({
        "track": "1", "admin_user": "jimmy",
        "password": "hemligt123", "password2": "hemligt123",
        "project_name": "acme",
    })
    status, body = _request(port, "POST", f"/apply?token={TOKEN}", fields)
    assert status == 200 and "✓" in body

    acl = yaml.safe_load((root / "config" / "acl.yaml").read_text())
    assert acl["users"]["jimmy"]["admin"] is True
    result = json.loads((root / ".setup-result.json").read_text())
    assert result["track"] == 1 and "password" not in json.dumps(result)

    # Självavstängande: servertråden dör av sig själv efter lyckad installation
    thread.join(timeout=5)
    assert not thread.is_alive()
