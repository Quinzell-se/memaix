#!/usr/bin/env python3
"""Memaix bootstrap — automatisk installation och provisionering.

SPDX-License-Identifier: AGPL-3.0-or-later

Vad detta gör:
  1. Säkerställer config-filer och genererar saknade hemligheter i .env.
  2. Startar containrarna (gateway + valfri cloudflared/nextcloud).
  3. Provisionerar Nextcloud automatiskt från config/acl.yaml:
       - skapar en NC-användare per projekt (ägare av projektets mapp/kalender)
       - mintar ett app-lösenord och skriver in det i .env under projektets *_ref
       - skapar projektmapp (WebDAV) och kalender (CalDAV)
  4. Seedar minnesvaults från vault-template/ och git-initierar dem.

KÖRS PÅ VÄRDEN. Kräver: docker, python3, pyyaml.
  pip install pyyaml && python3 scripts/bootstrap.py

OBS: occ-/OCS-anropen nedan stämmer med aktuella Nextcloud-versioner men bör valideras
mot just din image innan produktion. Detta är installationsautomation, inte en svart låda.
"""

from __future__ import annotations

import base64
import os
import secrets
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
ENV = ROOT / ".env"
NC_LOCAL = "http://127.0.0.1:8081"          # lokal Nextcloud (compose-port)


# ---------- helpers ----------

def sh(*args: str, **kw) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True, **kw).stdout.strip()


def occ(*args: str) -> str:
    """Kör occ i nextcloud-containern."""
    return sh("docker", "compose", "exec", "-T", "--user", "www-data", "nextcloud", "php", "occ", *args)


def env_get(key: str) -> str | None:
    if not ENV.exists():
        return None
    for line in ENV.read_text().splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return None


def env_set(key: str, value: str) -> None:
    lines = ENV.read_text().splitlines() if ENV.exists() else []
    out, found = [], False
    for line in lines:
        if line.startswith(f"{key}="):
            out.append(f"{key}={value}"); found = True
        else:
            out.append(line)
    if not found:
        out.append(f"{key}={value}")
    ENV.write_text("\n".join(out) + "\n")


def ensure_secrets() -> None:
    if not ENV.exists():
        ENV.write_text((ROOT / ".env.example").read_text())   # kopiera mall
    if not env_get("MEMAIX_OAUTH_SIGNING_KEY"):
        env_set("MEMAIX_OAUTH_SIGNING_KEY", secrets.token_hex(32))
    if not env_get("NEXTCLOUD_ADMIN_PASSWORD"):
        env_set("NEXTCLOUD_ADMIN_PASSWORD", secrets.token_hex(16))


def load_acl() -> dict:
    path = CONFIG / "acl.yaml"
    if not path.exists():
        sys.exit("config/acl.yaml saknas — kopiera från acl.example.yaml och fyll i.")
    return yaml.safe_load(path.read_text()) or {}


# ---------- nextcloud provisionering ----------

def nc_user_from_url(url: str) -> str | None:
    # .../remote.php/dav/files/<user>/...  → <user>
    parts = url.split("/dav/files/")
    return parts[1].split("/")[0] if len(parts) == 2 else None


def nc_app_password(user: str, password: str) -> str:
    """Minta ett app-lösenord via OCS för en användare."""
    req = urllib.request.Request(
        f"{NC_LOCAL}/ocs/v2.php/core/getapppassword",
        headers={
            "OCS-APIRequest": "true",
            "Authorization": "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode(),
            "Accept": "application/json",
        },
    )
    import json
    data = json.loads(urllib.request.urlopen(req).read())
    return data["ocs"]["data"]["apppassword"]


def provision_nextcloud(acl: dict) -> None:
    admin = env_get("NEXTCLOUD_ADMIN_USER") or "admin"
    for pname, proj in acl.get("projects", {}).items():
        files_url = proj.get("files")
        if not files_url:
            continue
        user = nc_user_from_url(files_url) or pname
        user_pw = secrets.token_hex(16)
        # 1) skapa användare (idempotent: ignorera om finns)
        try:
            occ("user:add", "--password-from-env", user, env={**os.environ, "OC_PASS": user_pw})
        except subprocess.CalledProcessError:
            print(f"  användare {user} finns redan — hoppar")
            continue
        # 2) app-lösenord → .env under projektets *_ref
        ref = proj.get("files_password_ref")
        if ref:
            env_set(ref, nc_app_password(user, user_pw))
        # 3) kalender
        occ("dav:create-calendar", user, "work")
        # 4) projektmapp skapas av första WebDAV-skrivningen; NC ger användaren en hemmamapp.
        print(f"  ✓ provisionerat projekt {pname} (nc-användare {user})")
    print("Nextcloud-provisionering klar.")


# ---------- vaults ----------

def seed_vaults(acl: dict) -> None:
    tpl = ROOT / "vault-template"
    vaults = ROOT / "vaults"
    for pname in list(acl.get("projects", {})) + ["shared"]:
        dest = vaults / pname
        if dest.exists():
            continue
        dest.mkdir(parents=True)
        src = tpl / ("shared" if pname == "shared" else "PROJECT-TEMPLATE")
        if src.exists():
            sh("cp", "-r", f"{src}/.", str(dest))
        sh("git", "-C", str(dest), "init", "-q")
        sh("git", "-C", str(dest), "add", "-A")
        sh("git", "-C", str(dest), "commit", "-qm", "seed", env={**os.environ,
           "GIT_AUTHOR_NAME": "memaix", "GIT_AUTHOR_EMAIL": "memaix@localhost",
           "GIT_COMMITTER_NAME": "memaix", "GIT_COMMITTER_EMAIL": "memaix@localhost"})
        print(f"  ✓ seedade vault {pname}")


def wait_for_nextcloud(timeout=300) -> None:
    print("Väntar på Nextcloud …")
    start = time.time()
    while time.time() - start < timeout:
        try:
            if "installed: true" in occ("status").lower().replace(" ", ""):
                return
        except subprocess.CalledProcessError:
            pass
        time.sleep(5)
    sys.exit("Nextcloud blev inte klar i tid.")


# ---------- main ----------

def main() -> None:
    profiles = []
    if "--tunnel" in sys.argv:
        profiles += ["--profile", "tunnel"]
    use_nc = "--no-nextcloud" not in sys.argv
    if use_nc:
        profiles += ["--profile", "nextcloud"]

    ensure_secrets()
    acl = load_acl()

    print("Startar containrar …")
    sh("docker", "compose", *profiles, "up", "-d")

    if use_nc:
        wait_for_nextcloud()
        provision_nextcloud(acl)

    seed_vaults(acl)
    print("\nKlart. Lägg in din connector-URL i AI:n — se docs/AI-CLIENTS.md.")


if __name__ == "__main__":
    main()
