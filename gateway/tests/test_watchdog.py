# SPDX-License-Identifier: AGPL-3.0-or-later
"""Väktarens rena beslutslogik (scripts/watchdog.py, Fas A).

Sidoeffekterna (docker/systemd/HTTP) övas i drift; här bevisas besluten:
vad som startas om, vad som bara rapporteras, och att notisformatet håller.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import watchdog  # noqa: E402


def test_extract_served_hash():
    html = '<script src="/app/static/app.js?v=e98dd16f2811" defer></script>'
    assert watchdog.extract_served_hash(html) == "e98dd16f2811"
    assert watchdog.extract_served_hash("<html>utan versionsref</html>") is None


def test_decide_restarts_targets_failing_service():
    assert watchdog.decide_restarts({"gateway": False, "hydra": True, "public": True}) == ["gateway"]
    assert watchdog.decide_restarts({"gateway": True, "hydra": False, "public": True}) == ["hydra"]


def test_decide_restarts_public_down_points_at_tunnel():
    # Publik nere men gateway frisk → tunnelkedjan, inte gatewayn.
    assert watchdog.decide_restarts({"gateway": True, "hydra": True, "public": False}) == ["cloudflared"]
    # Gateway nere OCH publik nere → gateway först; cloudflared pekas inte ut
    # (publik-felet förklaras av gatewayn).
    assert watchdog.decide_restarts({"gateway": False, "hydra": True, "public": False}) == ["gateway"]


def test_stale_frontend_and_ro_config_warn_but_never_restart():
    # Omstart läker inte en gammal image eller en :ro-mount — människans beslut.
    results = {"gateway": True, "hydra": True, "public": True,
               "frontend": False, "writable": False, "drift": 3}
    assert watchdog.decide_restarts(results) == []
    body = watchdog.build_notification(results, healed=[], still_red=[])
    assert "frontend" in body.lower() and "skrivbar" in body.lower() and "3 commits" in body


def test_notification_silent_when_green():
    results = {"gateway": True, "hydra": True, "public": True,
               "frontend": True, "writable": True, "drift": 0}
    assert watchdog.build_notification(results, healed=[], still_red=[]) == ""


def test_notification_red_beats_healed():
    body = watchdog.build_notification({}, healed=["gateway"], still_red=["hydra"])
    assert "RÖTT" in body and "hydra" in body
    assert "Självläkte" not in body, "rött efter omstart är huvudbudskapet — inte delseger"


def test_webhook_request_formats():
    url, data, headers = watchdog.build_webhook_request(
        "https://discord.com/api/webhooks/x", "discord", "Ämne", "rad1"
    )
    payload = json.loads(data)
    assert "Ämne" in payload["content"] and headers["Content-Type"] == "application/json"

    _, data, headers = watchdog.build_webhook_request("https://ntfy.sh/t", "raw", "Ämne", "rad1")
    assert data.decode().startswith("Ämne") and "text/plain" in headers["Content-Type"]


def test_all_http_goes_through_custom_user_agent(monkeypatch):
    # Cloudflare 403:ar Pythons default-UA — utan egen UA övervakar väktaren
    # Cloudflares botfilter i stället för Memaix (falsklarm + onödig omstart).
    captured = {}

    class _Resp:
        status = 200

        def read(self):
            return b""

    def fake_urlopen(req, timeout=None):
        captured["ua"] = req.headers.get("User-agent", "")
        return _Resp()

    monkeypatch.setattr(watchdog.urllib.request, "urlopen", fake_urlopen)
    assert watchdog._http_ok("https://example.com", 5) is True
    assert captured["ua"].startswith("memaix-watchdog/"), captured
