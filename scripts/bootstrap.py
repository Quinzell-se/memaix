#!/usr/bin/env python3
"""Memaix bootstrap — wizard (--init) och automatisk installation.

SPDX-License-Identifier: AGPL-3.0-or-later

Lägen:
  --init          Interaktiv wizard: genererar all config + hemligheter (front-dörren)
  --trial         Tier 0: lokal stdio-MCP, inget tunnel/OAuth/domän
  --tunnel        Tier 1: startar stacken med Cloudflare-tunnel
  --no-nextcloud  Hoppar över Nextcloud-provisionering

KÖRS PÅ VÄRDEN. Kräver: docker, python3.
"""

from __future__ import annotations

import base64
import getpass
import hashlib
import hmac
import os
import secrets
import subprocess
import sys
import textwrap
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
ENV = ROOT / ".env"
NC_LOCAL = "http://127.0.0.1:8081"


# ─────────────────────────────── helpers ────────────────────────────────────


def sh(*args: str, **kw) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True, **kw).stdout.strip()


def occ(*args: str) -> str:
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


def _fernet_key() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode()


def _pbkdf2_hash(password: str) -> str:
    salt = os.urandom(32)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return f"{salt.hex()}:{key.hex()}"


def ask(prompt: str, default: str = "", secret: bool = False) -> str:
    display = f"{prompt} [{default}]: " if default else f"{prompt}: "
    if secret:
        val = getpass.getpass(display)
    else:
        val = input(display).strip()
    return val if val else default


def choose(prompt: str, options: list[tuple[str, str]], default: int = 1) -> int:
    print(f"\n{prompt}")
    for i, (label, desc) in enumerate(options, 1):
        marker = "●" if i == default else " "
        print(f"  [{marker}{i}] {label}  — {desc}")
    while True:
        raw = input(f"  Välj [1–{len(options)}, default {default}]: ").strip()
        if not raw:
            return default
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return int(raw)


def hr() -> None:
    print("─" * 60)


# ─────────────────────────────── wizard ─────────────────────────────────────


def run_wizard() -> None:
    print()
    print("  ███╗   ███╗███████╗███╗   ███╗ █████╗ ██╗██╗  ██╗")
    print("  ████╗ ████║██╔════╝████╗ ████║██╔══██╗██║╚██╗██╔╝")
    print("  ██╔████╔██║█████╗  ██╔████╔██║███████║██║ ╚███╔╝ ")
    print("  ██║╚██╔╝██║██╔══╝  ██║╚██╔╝██║██╔══██║██║ ██╔██╗ ")
    print("  ██║ ╚═╝ ██║███████╗██║ ╚═╝ ██║██║  ██║██║██╔╝ ██╗")
    print("  ╚═╝     ╚═╝╚══════╝╚═╝     ╚═╝╚═╝  ╚═╝╚═╝╚═╝  ╚═╝")
    print()
    print("  Bring your own AI. Own your memory.")
    print()
    hr()
    print("  Wizarden genererar all config + hemligheter. Ingen YAML-redigering.")
    hr()

    # ── Spår ──────────────────────────────────────────────────────────────────
    track = choose(
        "Vad vill du göra?",
        [
            ("Prova lokalt",          "stdio, inget tunnel/OAuth/domän, ~5 min"),
            ("Self-host (mobil/team)", "tunnel + OAuth, nås från telefon/team"),
            ("Installera åt kund",    "som self-host men med eget domännamn"),
        ],
    )

    # ── Branding ──────────────────────────────────────────────────────────────
    name = ask("\nEget produktnamn (visas i OAuth-consent)", "Memaix")
    support_email = ask("Support-mejl", "support@example.com")

    # ── Domän & tunnel ────────────────────────────────────────────────────────
    public_url = "http://localhost:8080"
    tunnel_token = ""
    tunnel_provider = "none"

    if track in (2, 3):
        print()
        hr()
        domain = ask("Din domän för Memaix (t.ex. mcp.företag.se)")
        if not domain:
            print("  ⚠  Domän krävs för self-host. Kör om wizarden när du har en.")
            sys.exit(1)
        public_url = f"https://{domain}"

        tunnel_choice = choose(
            "Hur exponerar du Memaix?",
            [
                ("Cloudflare Tunnel",       "rekommenderas — ingen öppen port, auto-TLS"),
                ("Cloudflare Quick-tunnel", "temporär *.trycloudflare.com — bara för test"),
                ("Caddy/nginx (befintlig)", "du har redan en reverse proxy med TLS"),
                ("Tailscale Funnel",        "personligt bruk, ingen publik exponering"),
                ("ngrok",                   "snabb demo, betalt för stabil URL"),
            ],
        )

        if tunnel_choice == 1:
            tunnel_provider = "cloudflare"
            print(textwrap.dedent("""
              Skapa tunneln i Cloudflare Zero Trust → Networks → Tunnels → Create (Cloudflared).
              Peka hostname mot http://localhost:80  (eller http://caddy:80 i Docker-nätverk).
              Stäng av "Block AI Bots" under Security → Bots för det här hostnamnet.
            """).rstrip())
            tunnel_token = ask("Klistra in tunnel-token (lämna tom för att lägga till senare)", "")
        elif tunnel_choice == 2:
            tunnel_provider = "cloudflare-quick"
            print("  Quick-tunnel startas automatiskt. URL:en skrivs ut när stacken är uppe.")
        elif tunnel_choice == 3:
            tunnel_provider = "none"
            print(f"  Konfigurera din Caddy/nginx att proxya mot http://localhost:8080")
            print(f"  och sätt public_url till https://{domain}  (se docs/EXPOSE.md).")
        elif tunnel_choice == 4:
            tunnel_provider = "tailscale"
            print("  Kör:  tailscale funnel 8080")
            print("  och sätt public_url till din ts.net-adress.")
        elif tunnel_choice == 5:
            tunnel_provider = "ngrok"
            print("  Kör:  ngrok http 8080")
            print("  och uppdatera public_url i config/memaix.yaml med ngrok-URL:en.")

    # ── Admin-användare ────────────────────────────────────────────────────────
    print()
    hr()
    admin_user = ask("Admin-användarnamn", "admin")
    while True:
        pw1 = getpass.getpass(f"Lösenord för {admin_user}: ")
        pw2 = getpass.getpass("Bekräfta lösenord: ")
        if pw1 == pw2 and len(pw1) >= 8:
            break
        if pw1 != pw2:
            print("  ✗ Lösenorden matchar inte — försök igen.")
        else:
            print("  ✗ Lösenordet måste vara minst 8 tecken.")
    password_hash = _pbkdf2_hash(pw1)

    # ── Projekt ────────────────────────────────────────────────────────────────
    print()
    hr()
    project_name = ask("Namn på ditt första projekt", "shared")

    # ── Sammanfattning ─────────────────────────────────────────────────────────
    print()
    hr()
    print(f"  Produkt:   {name}")
    print(f"  URL:       {public_url}")
    print(f"  Tunnel:    {tunnel_provider}")
    print(f"  Admin:     {admin_user}")
    print(f"  Projekt:   {project_name}")
    hr()
    confirm = ask("Generera config och starta? [j/n]", "j")
    if confirm.lower() not in ("j", "y", "ja", "yes"):
        print("Avbrutet.")
        sys.exit(0)

    # ── Skriv config ───────────────────────────────────────────────────────────
    print("\nGenererar config och hemligheter …")
    CONFIG.mkdir(exist_ok=True)

    # brand.yaml
    (CONFIG / "brand.yaml").write_text(
        f'name: "{name}"\n'
        f'tagline: "Bring your own AI. Own your memory."\n'
        f'support_email: "{support_email}"\n'
        f'primary_color: "#4f46e5"\n'
        f'logo_path: ""\n'
    )

    # memaix.yaml
    issuer = public_url.rstrip("/") + "/"
    (CONFIG / "memaix.yaml").write_text(
        f'server:\n'
        f'  bind: "0.0.0.0:8080"\n'
        f'  public_url: "{public_url}"\n'
        f'\n'
        f'auth:\n'
        f'  issuer: "{issuer}"\n'
        f'  resource_server_url: "{issuer}"\n'
        f'\n'
        f'onboarding:\n'
        f'  enabled: true\n'
    )

    # acl.yaml
    vault_path = f'/srv/vaults/{project_name}'
    (CONFIG / "acl.yaml").write_text(
        f'users:\n'
        f'  {admin_user}:\n'
        f'    oauth_subjects:\n'
        f'      - {admin_user}\n'
        f'    grants:\n'
        f'      {project_name}: owner\n'
        f'      shared: owner\n'
        f'\n'
        f'projects:\n'
        f'  {project_name}:\n'
        f'    vault: {vault_path}\n'
        f'    allow_send: false\n'
        f'  shared:\n'
        f'    vault: /srv/vaults/shared\n'
        f'    allow_send: false\n'
    )

    # .env
    env_lines = [
        "# Genererat av make init — ändra inte för hand",
        f"CLOUDFLARE_TUNNEL_TOKEN={tunnel_token}",
        f"HYDRA_DB_PASSWORD={secrets.token_hex(32)}",
        f"HYDRA_SYSTEM_SECRET={secrets.token_hex(32)}",
        f"HYDRA_PUBLIC_URL={issuer}",
        f"HYDRA_LOGIN_URL={public_url.rstrip('/')}/login",
        f"HYDRA_CONSENT_URL={public_url.rstrip('/')}/consent",
        f"TOKEN_MASTER_KEY={_fernet_key()}",
        f"MEMAIX_ALLOWED_USERS={admin_user}",
        f"MEMAIX_LOGIN_PASSWORD_HASH={password_hash}",
        "NEXTCLOUD_ADMIN_USER=admin",
        f"NEXTCLOUD_ADMIN_PASSWORD={secrets.token_hex(16)}",
        "NEXTCLOUD_PUBLIC_HOST=",
    ]
    ENV.write_text("\n".join(env_lines) + "\n")
    ENV.chmod(0o600)

    print("  ✓ config/brand.yaml")
    print("  ✓ config/memaix.yaml")
    print("  ✓ config/acl.yaml")
    print("  ✓ .env  (hemligheter genererade, chmod 600)")

    # ── Seed vaults ────────────────────────────────────────────────────────────
    import yaml as _yaml
    acl = _yaml.safe_load((CONFIG / "acl.yaml").read_text()) or {}
    seed_vaults(acl)

    # ── Starta stack ───────────────────────────────────────────────────────────
    if track == 1:
        print("\nTrial-läge: starta stacken lokalt med:")
        print("  make up")
        print("\nAnslut Claude Desktop: lägg in path till gateway som stdio-MCP (se docs/AI-CLIENTS.md).")
    else:
        print("\nStartar stacken …")
        profiles = ["--profile", "hydra"]
        if tunnel_provider in ("cloudflare", "cloudflare-quick"):
            profiles += ["--profile", "tunnel"]
        sh("docker", "compose", *profiles, "up", "-d", cwd=str(ROOT))
        print(f"\n  ✓ Stacken uppe.")
        if tunnel_provider == "cloudflare-quick":
            print("  Hitta quick-tunnel-URL:en i loggarna:")
            print("  docker compose logs cloudflared | grep trycloudflare")
        else:
            print(f"\n  Connector-URL: {public_url}")
            print("  Lägg in den i din AI — se docs/AI-CLIENTS.md.")
        print("\n  Kör 'make doctor' för att verifiera att allt är grönt.")

    print()
    hr()
    print("  Klart! Lägg till backends och fler användare när du är redo:")
    print("  docs/BACKENDS.md  ·  docs/AI-CLIENTS.md  ·  docs/EXPOSE.md")
    hr()
    print()


# ─────────────────────────── befintliga funktioner ──────────────────────────


def ensure_secrets() -> None:
    if not ENV.exists():
        example = ROOT / ".env.example"
        if example.exists():
            ENV.write_text(example.read_text())
        else:
            ENV.write_text("")
    if not env_get("HYDRA_DB_PASSWORD"):
        env_set("HYDRA_DB_PASSWORD", secrets.token_hex(32))
    if not env_get("HYDRA_SYSTEM_SECRET"):
        env_set("HYDRA_SYSTEM_SECRET", secrets.token_hex(32))
    if not env_get("TOKEN_MASTER_KEY"):
        env_set("TOKEN_MASTER_KEY", _fernet_key())


def load_acl() -> dict:
    import yaml as _yaml
    path = CONFIG / "acl.yaml"
    if not path.exists():
        sys.exit("config/acl.yaml saknas — kör 'make init' eller kopiera från acl.example.yaml.")
    return _yaml.safe_load(path.read_text()) or {}


def nc_user_from_url(url: str) -> str | None:
    parts = url.split("/dav/files/")
    return parts[1].split("/")[0] if len(parts) == 2 else None


def nc_app_password(user: str, password: str) -> str:
    import json
    req = urllib.request.Request(
        f"{NC_LOCAL}/ocs/v2.php/core/getapppassword",
        headers={
            "OCS-APIRequest": "true",
            "Authorization": "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode(),
            "Accept": "application/json",
        },
    )
    data = json.loads(urllib.request.urlopen(req).read())
    return data["ocs"]["data"]["apppassword"]


def provision_nextcloud(acl: dict) -> None:
    for pname, proj in acl.get("projects", {}).items():
        files_url = proj.get("files")
        if not files_url:
            continue
        user = nc_user_from_url(files_url) or pname
        user_pw = secrets.token_hex(16)
        try:
            occ("user:add", "--password-from-env", user, env={**os.environ, "OC_PASS": user_pw})
        except subprocess.CalledProcessError:
            print(f"  användare {user} finns redan — hoppar")
            continue
        ref = proj.get("files_password_ref")
        if ref:
            env_set(ref, nc_app_password(user, user_pw))
        occ("dav:create-calendar", user, "work")
        print(f"  ✓ provisionerat projekt {pname} (nc-användare {user})")
    print("Nextcloud-provisionering klar.")


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
        try:
            sh("git", "-C", str(dest), "commit", "-qm", "seed", env={**os.environ,
               "GIT_AUTHOR_NAME": "memaix", "GIT_AUTHOR_EMAIL": "memaix@localhost",
               "GIT_COMMITTER_NAME": "memaix", "GIT_COMMITTER_EMAIL": "memaix@localhost"})
        except subprocess.CalledProcessError:
            pass  # tom vault, inget att commita
        print(f"  ✓ seedade vault {pname}")


def wait_for_nextcloud(timeout: int = 300) -> None:
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


def run_doctor() -> None:
    """Enkel hälsokontroll — körs av 'make doctor'."""
    import json, urllib.error
    ok = True

    def check(label: str, ok_: bool, hint: str = "") -> None:
        nonlocal ok
        status = "✓" if ok_ else "✗"
        print(f"  {status} {label}")
        if not ok_ and hint:
            print(f"      → {hint}")
        if not ok_:
            ok = False

    print("\nMemaix doctor\n")

    cfg_path = CONFIG / "memaix.yaml"
    check("config/memaix.yaml finns", cfg_path.exists(), "Kör 'make init'")
    check("config/acl.yaml finns", (CONFIG / "acl.yaml").exists(), "Kör 'make init'")
    check(".env finns", ENV.exists(), "Kör 'make init'")

    if cfg_path.exists():
        import yaml as _yaml
        cfg = _yaml.safe_load(cfg_path.read_text()) or {}
        pub = cfg.get("server", {}).get("public_url", "")
        check("public_url satt i memaix.yaml", bool(pub), "Sätt server.public_url")

        # Försök nå gateway lokalt
        try:
            urllib.request.urlopen("http://localhost:8080/health", timeout=3)
            check("Gateway svarar på :8080", True)
        except Exception:
            check("Gateway svarar på :8080", False, "docker compose logs gateway")

        # Försök nå Hydra lokalt
        try:
            urllib.request.urlopen("http://localhost:4444/.well-known/openid-configuration", timeout=3)
            check("Hydra svarar på :4444", True)
        except Exception:
            check("Hydra svarar på :4444", False, "docker compose logs hydra")

    if ok:
        print("\n  Allt grönt.\n")
    else:
        print("\n  Åtgärda felen ovan och kör om 'make doctor'.\n")
        sys.exit(1)


# ─────────────────────────────── main ───────────────────────────────────────


def main() -> None:
    args = sys.argv[1:]

    if "--init" in args:
        try:
            import yaml  # noqa: F401
        except ImportError:
            subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "pyyaml"], check=True)
        run_wizard()
        return

    if "--doctor" in args:
        run_doctor()
        return

    # Legacy install-läge
    profiles = []
    if "--tunnel" in args:
        profiles += ["--profile", "tunnel"]
    use_nc = "--no-nextcloud" not in args
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
