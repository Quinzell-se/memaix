# Bygg-spec — gateway-implementationen

Specen för den som implementerar (eller låter en AI-kodassistent implementera) Memaix-gatewayen.

## Stack
- **Python.** MCP Python SDK / FastMCP med **Streamable HTTP-transport**. Auth via **ory Hydra**
  (certifierad OAuth2/DCR) — gatewayen **validerar tokens** (bygger ingen egen OAuth-server). Kör som
  container (se `gateway/Dockerfile`).

## Moduler (se `gateway/src/memaix_gateway/`)
- `config.py` — läs `config/*.yaml` + `.env`, lös `*_ref` mot env.
- `acl.py` — ladda acl.yaml; `check(user, project, role)`-enforcement. **Klart specat — börja här.**
- `auth/` — token-validering mot Hydra (JWKS), mappar OAuth-subject → intern användare.
- `server.py` — MCP-server, registrerar verktyg, kör AuthZ före varje anrop.
- `tools/email.py | calendar.py | files.py | memory.py | backlog.py` — verktygen.

## Verktyg & roller
Alla verktyg tar `project` och valideras mot acl.yaml innan körning.

| Verktyg | Roll | Backend |
|---|---|---|
| `email_list/read/search/create_draft` | collaborator | IMAP/SMTP |
| `email_send` | owner (+ `allow_send`) | SMTP |
| `calendar_*` | collaborator | CalDAV |
| `files_*` | collaborator | WebDAV |
| `memory_read/search` | reader | git-vault |
| `memory_append/write` | collaborator | SQLite (aktivt) + git async (historik) |
| `memory_history/revert` | reader / collaborator | git |
| `backlog_add/score/comment` | collaborator | markdown i vault |
| `backlog_set_status` | owner | markdown i vault |
| `whoami` | alla | acl |

## Faser
1. **Skelett + ACL (stdio).** config + acl + `whoami` + ett projekt med `files_*` mot lokal mapp.
   Verifiera att användare utan grant nekas. **Detta bevis måste finnas före allt annat.**
1b. **Config-wizard (tidig, grafisk uppsättning).** Tunn webb/CLI som *skriver och validerar*
   `acl.yaml`/`memaix.yaml`/`.env` — lägg till projekt, användare, roller, secret-`*_ref`. Beror bara
   på config-schemat (stabilt), **inte** på backends → kan byggas nu. Skriver bara config + kör
   schemavalidering; provisionerar inget ännu. Se `SETUP-UI.md`.
2. **Backends.** email/calendar/files/memory/backlog. Testa via lokal kodassistent (stdio).
3. **Remote + auth.** Streamable HTTP + Hydra (token-validering). Exponera via tunnel.
4. **RBAC skarpt.** Alla projekt/roller; verifiera isolering mellan projekt.
5. **Koppla in AI.** Lägg connectorn på webben; testa OAuth från mobil.
6. **Onboarding + flerpersoner.** Profil-intervju, externa med ett projekt.

> **Safety-motorn (`SAFETY.md`) byggs parallellt från Fas 2 — inte som en sista fas.**
> **Provisionerings-stegen** (Nextcloud-konton, OAuth-länkning, tunnel-setup, doctor mot levande
> tjänster) växer in i wizarden **funktion för funktion i takt med respektive backend** (Fas 2–5) —
> inte i Fas 1b, som bara skriver config.

## Minne & backlog (SQLite aktivt + git async)
- **Aktivt tillstånd i SQLite** (transaktioner, samtidighet); kunskapsnoteringar som markdown. Git
  tar historiken **asynkront** (batchade snapshots) — inte commit-per-skrivning. `memory_history`/
  `memory_revert` = git-logg/revert. Se `SAFETY.md` + `REVIEW-RESPONSE.md`.
- Backlog-item = markdown med frontmatter (id, title, author, category, status, value, complexity,
  risk). Statusflöde: inbox → triaged → evaluated → approved/rejected → in-dev → done.

## Onboarding
Vid `whoami` där `om-<user>.md` saknas eller har `profil_status: ofullständig` → kör
`shared/onboarding-interview.md`: intervjua, sammanställ till `om-<user>.md`, sätt `profil_status: klar`.
