#!/usr/bin/env python3
"""Memaix väktare — Fas A i SELF-IMPROVING-SYSTEM.md.

SPDX-License-Identifier: AGPL-3.0-or-later

Körs av systemd-timern memaix-watchdog.timer (var 6:e timme + vid boot).
KÖRS PÅ VÄRDEN. Enbart stdlib + pyyaml (samma krav som bootstrap.py).

Loopen: kontrollera → självläk (omstart av felande tjänst, EN gång) →
kontrollera igen → notifiera vid avvikelse. Tyst när allt är grönt.

Kontroller (varav två automatiserar AGENTS.md §6b regel 1–2):
  gateway   — :8080/health lokalt
  hydra     — :4444/.well-known lokalt
  publik    — public_url/app genom tunnel/CDN
  frontend  — hash i publikt serverad HTML == hash av app.js på disk
              ("verifiera det publicerade, inte det deployade")
  skrivbar  — /app/config går att skriva i containern
  drift     — klonen ligger efter origin/main (info, ingen åtgärd)

Självläkning = `docker compose restart` av felande tjänst. Väktaren
pullar aldrig, bygger aldrig, deployar aldrig (anti-hype-listan är bindande).

Notis: WATCHDOG_WEBHOOK_URL i .env (WATCHDOG_WEBHOOK_FMT: raw | discord —
samma semantik som notify-lagrets WebhookChannel). Utan URL: journalen.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"
_ASSET = ROOT / "gateway" / "src" / "memaix_gateway" / "web" / "static" / "app.js"
_ASSET_REF = re.compile(r"app\.js\?v=([0-9a-f]+)")

# Tjänst → hur felet läks. frontend/skrivbar/drift läks inte av omstart
# (kräver rebuild/compose-ändring/deploy = människans beslut) — bara notis.
_RESTARTABLE = ("gateway", "hydra", "public")


# ───────────────────────── rena hjälpare (testade) ─────────────────────────


def extract_served_hash(html: str) -> str | None:
    """Versionshashen ur publikt serverad HTML, eller None."""
    m = _ASSET_REF.search(html)
    return m.group(1) if m else None


def local_asset_hash(path: Path = _ASSET) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def decide_restarts(results: dict) -> list:
    """Vilka tjänster som ska startas om, givet kontrollresultaten.
    public-fel med frisk gateway pekar på tunnelkedjan → cloudflared."""
    restarts = []
    if not results.get("gateway", True):
        restarts.append("gateway")
    if not results.get("hydra", True):
        restarts.append("hydra")
    if not results.get("public", True) and results.get("gateway", True):
        restarts.append("cloudflared")
    return restarts


def build_notification(results: dict, healed: list, still_red: list) -> str:
    lines = []
    if still_red:
        lines.append(f"🔴 RÖTT efter omstart: {', '.join(still_red)} — manuell åtgärd krävs.")
    if healed and not still_red:
        lines.append(f"🟡 Självläkte: {', '.join(healed)} startades om och är gröna igen.")
    if results.get("frontend") is False:
        lines.append("⚠️ Publik frontend serverar INTE diskens app.js — "
                     "rebuild/deploy saknas eller CDN-cache (AGENTS §6b regel 1).")
    if results.get("writable") is False:
        lines.append("⚠️ /app/config är INTE skrivbar i containern — "
                     "admin-skrivvägarna är brutna (AGENTS §6b regel 2).")
    if results.get("drift", 0) > 0:
        lines.append(f"ℹ️ Klonen ligger {results['drift']} commits efter origin/main.")
    return "\n".join(lines)


def build_webhook_request(url: str, fmt: str, subject: str, body: str):
    """(url, data-bytes, headers) för notisen — discord-JSON eller rå text."""
    if fmt == "discord":
        data = json.dumps({"content": f"**{subject}**\n{body}"}).encode()
        headers = {"Content-Type": "application/json"}
    else:
        data = f"{subject}\n{body}".encode()
        headers = {"Content-Type": "text/plain; charset=utf-8"}
    return url, data, headers


# ───────────────────────── kontroller (sidoeffekter) ────────────────────────


def _env_get(key: str) -> str:
    if not ENV.exists():
        return ""
    for line in ENV.read_text().splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return ""


def _http_ok(url: str, timeout: int = 10) -> bool:
    try:
        urllib.request.urlopen(url, timeout=timeout)
        return True
    except Exception:
        return False


def _public_url() -> str:
    import yaml

    cfg = yaml.safe_load((ROOT / "config" / "memaix.yaml").read_text()) or {}
    return (cfg.get("server") or {}).get("public_url", "").rstrip("/")


def run_checks() -> dict:
    results: dict = {}
    results["gateway"] = _http_ok("http://localhost:8080/health", 5)
    results["hydra"] = _http_ok("http://localhost:4444/.well-known/openid-configuration", 5)

    public = _public_url()
    html = ""
    if public:
        try:
            html = urllib.request.urlopen(f"{public}/app", timeout=15).read().decode()
            results["public"] = True
        except Exception:
            results["public"] = False

    served, local = extract_served_hash(html), local_asset_hash()
    if served and local:
        results["frontend"] = served == local
    # utan båda hasharna: ingen dom — hellre tyst än falsklarm

    probe = subprocess.run(
        ["docker", "exec", "memaix-gateway-1", "sh", "-c",
         "touch /app/config/.watchdog && rm /app/config/.watchdog"],
        capture_output=True,
    )
    results["writable"] = probe.returncode == 0

    subprocess.run(["git", "-C", str(ROOT), "fetch", "origin", "--quiet"],
                   capture_output=True, timeout=60)
    drift = subprocess.run(
        ["git", "-C", str(ROOT), "rev-list", "--count", "HEAD..origin/main"],
        capture_output=True, text=True,
    )
    results["drift"] = int(drift.stdout.strip() or 0) if drift.returncode == 0 else 0
    return results


def restart_service(service: str) -> None:
    subprocess.run(
        ["docker", "compose", "--profile", "hydra", "--profile", "tunnel",
         "restart", service],
        capture_output=True, cwd=str(ROOT), timeout=180,
    )


def notify(subject: str, body: str) -> None:
    print(f"{subject}\n{body}")  # journalen, alltid
    url = _env_get("WATCHDOG_WEBHOOK_URL")
    if not url:
        return
    fmt = _env_get("WATCHDOG_WEBHOOK_FMT") or "raw"
    target, data, headers = build_webhook_request(url, fmt, subject, body)
    try:
        urllib.request.urlopen(
            urllib.request.Request(target, data=data, headers=headers), timeout=15
        )
    except Exception as exc:
        print(f"watchdog: notis misslyckades: {type(exc).__name__}", file=sys.stderr)


# ─────────────────────────────── main ───────────────────────────────────────


def main() -> int:
    results = run_checks()
    to_restart = decide_restarts(results)

    healed: list = []
    still_red: list = []
    if to_restart:
        for svc in to_restart:
            print(f"watchdog: startar om {svc} …")
            restart_service(svc)
        time.sleep(15)
        after = run_checks()
        for svc in to_restart:
            key = "public" if svc == "cloudflared" else svc
            (healed if after.get(key) else still_red).append(svc)
        results = after

    body = build_notification(results, healed, still_red)
    if body:
        notify("Memaix väktare", body)
    else:
        print("watchdog: allt grönt.")
    return 1 if still_red else 0


if __name__ == "__main__":
    sys.exit(main())
