# SPDX-License-Identifier: AGPL-3.0-or-later
"""Admin AI-val (/app/api/admin/llm) — CHOOSE-YOUR-LLM.md:s model-block.

Kontraktet: admin+MFA krävs, nyckeln lämnar aldrig servern (has_key bara),
nyckeln hamnar i config/secrets/llm_api_key (0600) med file:-ref — aldrig
i YAML — och byo tar bort hela model-blocket.
"""

from __future__ import annotations

import pytest
import yaml
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from memaix_gateway.web.api import admin_llm as mod


class _Audit:
    def __init__(self):
        self.entries = []

    def log(self, *a, **kw):
        self.entries.append((a, kw))


@pytest.fixture()
def rig(tmp_path, monkeypatch):
    (tmp_path / "memaix.yaml").write_text(
        'server:\n  public_url: "https://mcp.example.se"\n'
    )
    audit = _Audit()
    allowed = {"granted": True}
    monkeypatch.setattr(
        mod, "_require_admin_mfa",
        lambda request: ((("root", None), None) if allowed["granted"]
                         else (None, __import__("starlette.responses", fromlist=["JSONResponse"])
                               .JSONResponse({"error": "forbidden"}, status_code=403))),
    )
    monkeypatch.setattr(mod, "_config_dir", lambda: tmp_path)
    monkeypatch.setattr(mod, "_audit", lambda: audit)
    monkeypatch.setattr(
        mod, "_current_model",
        lambda: (yaml.safe_load((tmp_path / "memaix.yaml").read_text()) or {}).get("model") or {},
    )

    app = Starlette(routes=[
        Route("/app/api/admin/llm", mod.api_admin_llm_get, methods=["GET"]),
        Route("/app/api/admin/llm", mod.api_admin_llm_set, methods=["PUT"]),
    ])
    return TestClient(app), tmp_path, audit, allowed


def test_requires_admin(rig):
    client, _, _, allowed = rig
    allowed["granted"] = False
    assert client.get("/app/api/admin/llm").status_code == 403
    assert client.put("/app/api/admin/llm", json={"provider": "anthropic"}).status_code == 403


def test_get_default_is_byo(rig):
    client, _, _, _ = rig
    data = client.get("/app/api/admin/llm").json()
    assert data["provider"] == "byo" and data["has_key"] is False
    assert "anthropic" in data["providers"] and "ollama" in data["providers"]


def test_set_api_provider_stores_key_as_file_ref(rig):
    client, root, audit, _ = rig
    resp = client.put("/app/api/admin/llm", json={
        "provider": "anthropic", "name": "claude-sonnet-4-5", "api_key": "sk-ant-hemlig",
    })
    assert resp.status_code == 200 and resp.json()["has_key"] is True
    assert "sk-ant-hemlig" not in resp.text, "nyckeln får aldrig ekas tillbaka"

    cfg = yaml.safe_load((root / "memaix.yaml").read_text())
    model = cfg["model"]
    assert model["provider"] == "anthropic" and model["name"] == "claude-sonnet-4-5"
    assert model["api_key_ref"].startswith("file:"), "ref i YAML — aldrig nyckeln"
    assert "sk-ant-hemlig" not in yaml.safe_dump(cfg)
    assert cfg["server"]["public_url"] == "https://mcp.example.se", "övriga sektioner orörda"

    key_file = root / "secrets" / "llm_api_key"
    assert key_file.read_text().strip() == "sk-ant-hemlig"
    assert key_file.stat().st_mode & 0o777 == 0o600
    assert audit.entries and "sk-ant" not in str(audit.entries), "audit utan hemligheter"


def test_api_provider_requires_key(rig):
    client, _, _, _ = rig
    resp = client.put("/app/api/admin/llm", json={"provider": "openai", "name": "gpt-5"})
    assert resp.status_code == 400 and "api_key" in resp.json()["error"]


def test_endpoint_provider_local_net_or_cloud_instance(rig):
    client, root, _, _ = rig
    # LLM på lokala nätet — ingen nyckel behövs
    resp = client.put("/app/api/admin/llm", json={
        "provider": "ollama", "name": "qwen3-coder:30b",
        "endpoint": "http://192.168.1.20:11434",
    })
    assert resp.status_code == 200
    model = yaml.safe_load((root / "memaix.yaml").read_text())["model"]
    assert model["endpoint"] == "http://192.168.1.20:11434" and "api_key_ref" not in model

    # utan endpoint → 400
    resp = client.put("/app/api/admin/llm", json={"provider": "vllm", "name": "x"})
    assert resp.status_code == 400 and "endpoint" in resp.json()["error"]


def test_key_kept_when_not_resent(rig):
    client, root, _, _ = rig
    client.put("/app/api/admin/llm", json={
        "provider": "anthropic", "name": "claude-sonnet-4-5", "api_key": "sk-behåll",
    })
    # Byt bara modellnamn — ingen ny nyckel skickas
    resp = client.put("/app/api/admin/llm", json={
        "provider": "anthropic", "name": "claude-opus-4-8",
    })
    assert resp.status_code == 200 and resp.json()["has_key"] is True
    model = yaml.safe_load((root / "memaix.yaml").read_text())["model"]
    assert model["name"] == "claude-opus-4-8" and model["api_key_ref"].startswith("file:")
    assert (root / "secrets" / "llm_api_key").read_text().strip() == "sk-behåll"


def test_byo_removes_model_block(rig):
    client, root, _, _ = rig
    client.put("/app/api/admin/llm", json={
        "provider": "openrouter", "name": "anthropic/claude-sonnet-4-5", "api_key": "sk-or",
    })
    resp = client.put("/app/api/admin/llm", json={"provider": "byo"})
    assert resp.status_code == 200
    cfg = yaml.safe_load((root / "memaix.yaml").read_text())
    assert "model" not in cfg
    assert cfg["server"]["public_url"] == "https://mcp.example.se"


def test_rejects_unknown_provider_and_bad_endpoint(rig):
    client, _, _, _ = rig
    assert client.put("/app/api/admin/llm", json={"provider": "skynet"}).status_code == 400
    resp = client.put("/app/api/admin/llm", json={
        "provider": "ollama", "name": "x", "endpoint": "gopher://nej",
    })
    assert resp.status_code == 400
