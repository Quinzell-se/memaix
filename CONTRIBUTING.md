# Bidra till Memaix

Tack för att du vill bidra! Läs detta innan du öppnar en PR. Bygg-/arkitekturkontext: `HANDOFF.md`
och `docs/INDEX.md`.

## Licens & rättigheter (viktigt)
Memaix-koden är **AGPL-3.0-or-later** och **dual-licensieras** (en kommersiell licens säljs till dem
som inte kan använda AGPL, samt enterprise-moduler). Därför gäller **både** DCO och CLA:

### DCO — Developer Certificate of Origin
Varje commit ska vara signerad:
```
git commit -s        # lägger till: Signed-off-by: Ditt Namn <din@mejl>
```
Sign-off intygar att du har rätt att bidra koden under projektets licens (se developercertificate.org).

### CLA — Contributor License Agreement
Eftersom vi dual-licensierar behöver vi rätt att **relicensiera** ditt bidrag (annars kan vi inte sälja
en kommersiell licens av hela koden). Första PR:en triggar **CLA Assistant** — du signerar en gång.
Utan CLA kan vi tyvärr inte slå ihop bidraget. *(Kör vi bara DCO i framtiden faller detta bort.)*

## Innan du öppnar PR
- **Tester:** lägg/uppdatera tester (se `docs/TESTING.md`) — särskilt för den deterministiska motorn
  och RBAC-enforcement.
- **Docs-hygien:** `python3 scripts/check-docs-index.py` ska vara grön (nytt `docs/*.md` → in i INDEX).
- **Säkerhet:** följ `docs/THREAT-MODEL.md` och `docs/SAFETY.md` — inga genvägar kring RBAC,
  injection-skydd eller secret-scrubbing.
- **SPDX-header** i nya källfiler: `SPDX-License-Identifier: AGPL-3.0-or-later`.

## Stil
Skriv kod som liknar omgivande kod. Håll dokument korta och konkreta (jfr befintliga docs).
