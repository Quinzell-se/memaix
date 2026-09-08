#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Rökprov som körs INUTI gateway-imagen, mot en bind-monterad vault.

Testsviten kör som samma uid som äger filerna den skapar. Produktionen gör
inte det: containern kör som ett uid, bind-mounten ägs av värdens. Git >=2.35
vägrar då operera ("detected dubious ownership", exit 128) på varje kommando,
och koden svalde det — sex av sju valv i produktion innehöll noll commits
medan `memory_write` returnerade något som såg ut som en hash. 1 260 gröna
tester samexisterade med det i månader.

Det här provet är den saknade våningen: samma image, samma monteringar, båda
ägarskapsfallen.

  friendly   containerns uid äger vaulten. En skrivning ska ge en hash som git
             SJÄLV kan slå upp, och historiken ska se den. Att asserta att
             returvärdet är en sträng räcker inte -- "" är också en sträng,
             och det var precis vad produktionen lämnade tillbaka.

  hostile    containerns uid äger den inte. Skrivningen ska braka. Att den
             skulle lyckas vore fel; att den returnerar tomt utan att säga
             något är värre, för då är vi tillbaka i tystnaden som kostade
             oss månaderna.

Anropar verktygslagret (tools.memory) snarare än MCP-verktygen över HTTP:
HTTP-läget failar stängt utan verifierad OAuth-subject (server.py:198-203),
så en HTTP-väg hade krävt en Hydra i CI. Allt under identitetslagret -- ACL,
vaultupplösning, git, monteringar, imagen -- körs skarpt här. Identitets- och
transportlagret täcks av tests_e2e.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from memaix_gateway.acl import Acl
from memaix_gateway.config import load
from memaix_gateway.tools import memory as t_memory

PROJECT = "smoke"
USER = "smoke"
NOTE = "rokprov.md"
VAULT = Path("/srv/vaults/smoke")


def _acl() -> Acl:
    return Acl.from_config(load()["acl"])


def friendly() -> None:
    """Rätt ägarskap: hela kedjan ska leverera ett riktigt snapshot-id."""
    acl = _acl()

    written = t_memory.memory_write(
        acl, USER, PROJECT, NOTE, "rökprov: containern skriver till en monterad vault\n"
    )
    commit = written.get("commit") or ""
    if not commit:
        raise SystemExit(
            "FAIL: memory_write gav en tom commit -- exakt produktionsbuggen. "
            f"Svar: {written!r}"
        )

    # Hashen är bara ett löfte tills git går med på att slå upp den. En sträng
    # som ser ut som en hash men inte går att revert:a är inget snapshot-id.
    resolved = subprocess.run(  # noqa: S603
        ["git", "-C", str(VAULT), "rev-parse", "--verify", f"{commit}^{{commit}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if resolved.returncode != 0:
        raise SystemExit(
            f"FAIL: git kan inte slå upp {commit!r} i {VAULT}. {resolved.stderr.strip()}"
        )

    history = t_memory.memory_history(acl, USER, PROJECT, NOTE)
    if not history:
        raise SystemExit(
            "FAIL: memory_history gav [] för en not som just committades. "
            "Det är den tysta lögnen produktionen levde med."
        )
    if not any(h.get("hash", "").startswith(commit[:7]) for h in history):
        raise SystemExit(
            f"FAIL: historiken saknar {commit!r}. Fick: {history!r}"
        )

    print(f"OK friendly: commit {commit[:12]}, {len(history)} rad(er) historik")


def hostile() -> None:
    """Fel ägarskap: felet ska höras, inte sväljas."""
    acl = _acl()

    try:
        written = t_memory.memory_write(
            acl, USER, PROJECT, NOTE, "rökprov: fel uid, detta ska inte gå igenom\n"
        )
    except Exception as exc:  # noqa: BLE001 -- felets typ är mindre viktig än att det hörs
        detail = f"{type(exc).__name__}: {exc}"
        # Att något kastade räcker inte. Första versionen av provet dog på
        # "attempt to write a readonly database" och nådde aldrig git -- rätt
        # utfall av fel skäl, och därmed blind för en regression där git blir
        # tyst igen. Kräv att felet kommer från det lager provet finns för.
        if "git" not in detail.lower():
            raise SystemExit(
                "FAIL: skrivningen braket, men inte i git -- provet nådde aldrig "
                f"lagret det finns för. Fick: {detail}"
            ) from exc
        print(f"OK hostile: git vägrade högljutt -- {detail}")
        return

    commit = written.get("commit") or ""
    if not commit:
        raise SystemExit(
            "FAIL: memory_write returnerade tom commit i stället för att kasta. "
            "Det här är regressionen -- tyst fel som ser ut som framgång."
        )
    raise SystemExit(
        f"FAIL: skrivningen lyckades ({commit[:12]}) trots främmande ägarskap. "
        f"Provet mäter inte det det tror att det mäter -- kontrollera uid-uppsättningen."
    )


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    print(f"-- rökprov {mode!r} som uid {os.getuid()}:{os.getgid()}", flush=True)
    if mode == "friendly":
        friendly()
    elif mode == "hostile":
        hostile()
    else:
        raise SystemExit(f"okänt läge {mode!r} -- välj 'friendly' eller 'hostile'")


if __name__ == "__main__":
    main()
