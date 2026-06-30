# Överlämning → lokala bygg-sessionen (qronkclawd)

> **Vision:** en AI-agnostisk ingång till team-gemensamt minne (projekt-, person-, utvecklingskunskap)
> + en projektledaragent som håller koll på vad/vem/när/beroenden/konsekvenser. Hjärnan minns, agenten agerar.

Läs detta först, sedan **`AGENTS.md`** (hårda guardrails för den byggande AI:n — bindande). Allt
material (plan, specar, utvecklingsinstruktioner, vault-utkast) ligger i git-repot
`Quinzell-se/memaix`. Inget viktigt ligger utanför repot.

## 1. Hämta hem allt
```bash
# Om repot inte redan finns lokalt:
git clone git@github.com:Quinzell-se/memaix.git && cd memaix
```
Allt produktmaterial ligger i roten av repot. Alice & Bob egen driftplan ligger under
**`docs/ai-assistent-plattform.md`** + seed-innehåll i **`docs/vault-utkast/`**.

## 2. Två spår (samma kod)
1. **Bygg produkten Memaix** — gatewayen, generaliserad. Specar i `memaix/`.
2. **Kör en instans för oss** — samma gateway, konfigurerad för Alice's/Bob's projekt, seedad med
   `docs/vault-utkast/`.

## 3. Läs i ordning
Startpunkt: **`memaix/docs/INDEX.md`** (rollsektionen "🏗️ Ska du bygga gatewayen?"). Minst:
`ARCHITECTURE.md` → `MCP-API.md` → `BUILD.md` → **`REVIEW-RESPONSE.md`** → **`SAFETY.md`**.

## 4. AUKTORITATIVA v2-beslut (gäller ÖVER äldre formuleringar)
Efter två oberoende granskningar (se `REVIEW-RESPONSE.md`) ändrades följande — där en äldre doc säger
annorlunda, gäller detta:
- **Auth:** bygg på **ory Hydra** (certifierad OAuth2/DCR), **inte** egen OAuth-server. Gateway
  validerar tokens; tunn login/consent-UI. Tunnel = ren proxy (ingen Access).
- **Minne:** **SQLite som aktivt tillstånd** + **git asynkront** för historik. Inte commit-per-skrivning.
- **Safety-motor (obligatorisk, `SAFETY.md`):** rate limiting, circuit breakers, budgetar,
  loop-detektion, concurrency-kontroll, context-/retrieval-disciplin (dumpa aldrig), data-retention/
  purge, **bekräftelse för destruktiva åtgärder**, **MFA för admin/setup**.
- **Mejl:** BYO-infra, **ingen reseller**. Behåll *projektspecifik mejl-provisionering* i kundens
  egna leverantör för tillfälliga konsulter (`MAIL.md`).
- **iOS:** kärnkrav, via remote connector (kör i AI-leverantörens moln). Skjut inte upp.
- **Audit:** basal audit i kärnan, inte bara enterprise.

## 5. Byggordning (Fas 1 →, från `BUILD.md` med v2-deltan)
1. **Skelett + ACL (stdio):** `config.py` + `acl.py` finns redan i `memaix/gateway/`. Lägg `whoami`
   + ett projekt (`acme`) med `files_*` mot lokal mapp. **Verifiera RBAC-isolering** (användare
   utan grant nekas) — detta bevis först.
1b. **Config-wizard (tidig):** tunn webb/CLI som skriver + validerar `acl.yaml`/`memaix.yaml`/`.env`
   (projekt, användare, roller, secret-`*_ref`). Beror bara på config-schemat → kan byggas nu; skriver
   bara config, provisionerar inget. Ger Alice grafisk projekt/användar-uppsättning tidigt.
2. **Backends:** `email_*`/`calendar_*`/`files_*`/`memory_*`/`backlog_*`. Minne = SQLite + git async.
3. **Safety-motor** parallellt — inte sist. Provisionerings-stegen (Nextcloud/OAuth-länk/tunnel/doctor)
   växer in i wizarden i takt med respektive backend, inte i Fas 1b.
4. **Remote + auth:** Streamable HTTP + **Hydra**. Exponera via cloudflared. **Doctor** grön.
5. **RBAC skarpt + onboarding + per-användar-OAuth** (`PER-USER-OAUTH.md`).

## 6. Vår egen instans (deployment-config)
- **Projekt:** `acme`, `project-a`, `project-b`, `personal`, `shared`.
- **Personer:** `alice` (owner överallt), `bob` (owner project-a, collaborator acme + shared),
  `carol` (collaborator endast acme).
- **Backends:** acme-mejl = Purelymail (`alice@acme.com`); kalender/filer = Nextcloud;
  `personal` = Google (alice@personal.example.com). Övriga enligt behov.
- **Tunnel:** cloudflared → `mcp.acme.com` (samma mönster som vault.example.com).
- **Seed:** kopiera `docs/vault-utkast/` → instansens vaults; git-initiera per projekt.
- **Hemligheter:** i `.env`/secret store på qronkclawd — aldrig i repot.

## 7. Verifiera
- `cd memaix && python3 scripts/check-docs-index.py` (doc-hygien).
- Efter bygge: `doctor` (`DOCTOR.md`) — grönt innan "klart".

## Noteringar
- Historik migrerad från `your-monorepo` med `git subtree split` (2026-06-30).
- En äldre scratchpad-byggbrief (`qronk-mcp-gateway-brief.md`) är **ersatt** av `docs/BUILD.md`
  + detta dokument. Använd repot som sanningskälla.
