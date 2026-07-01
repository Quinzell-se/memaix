# Utvecklingsförslag — kodgranskning av gateway

SPDX-License-Identifier: AGPL-3.0-or-later

Prioriterade förslag från en genomgång av den implementerade gatewayen
(`gateway/src/memaix_gateway/`), board:en, login-appen och deploy-configen.
Till skillnad från [OPEN-GAPS.md](OPEN-GAPS.md) (luckor i *planeringen*) handlar
det här om den *befintliga koden*: konkreta buggar, säkerhetshål och
förbättringar med fil-referens och åtgärd.

Sorterat på effekt. De sex första säkerhetsfynden är **åtgärdade** i samma
granskningsomgång (se [SECURITY.md](SECURITY.md) och kodkommentarerna); de
kvarstående är arkitektur-/processförslag.

## Sammanfattning

| # | Förslag | Typ | Status |
|---|---------|-----|--------|
| 1 | Centraliserad sökvägsvalidering | Säkerhet | ✅ åtgärdat |
| 2 | Aktivera JWT `aud`-verifiering + lås DCR | Säkerhet | ✅ åtgärdat (aud) |
| 3 | CI som riktigt skyddsnät (kör testerna) | Process | ✅ åtgärdat |
| 4 | Fleranvändar-auth + ACL på board:en | Säkerhet | ✅ authz åtgärdat |
| 5 | Enhetlig behörighets-/audit-hjälpare | Arkitektur | ✅ åtgärdat |
| 6 | Delat tillstånd till backend (SQLite) | Arkitektur | ✅ åtgärdat |
| 7 | Robust OAuth-konto-identitet | Bugg | ✅ åtgärdat |
| 8 | Härda alla externa I/O-anrop | Säkerhet | ✅ IMAP/git åtgärdat |
| 9 | Strukturerad loggning + observability | Drift | ✅ logger åtgärdat |
| 10 | Robust datamodell för backlog/PM | Arkitektur | ✅ åtgärdat |

---

## 1. Centralisera sökvägsvalidering

**Problem.** `backlog.py`, `pm.py` och `board/store.py` bygger sökvägar som
`vault / "backlog" / f"{id}.md"` utan att validera `id`/`sprint_id`. Det ger
path traversal: `backlog_get(..., id="../../secret")` läser en fil *utanför*
vaulten, och `pm_plan_sprint`/`backlog_score` kan skriva utanför den.
`memory.py` gör rätt via `_validate_note_path` — men skyddet var inte delat.

**Åtgärd.** Bryt ut valideringen till en delad `paths.py` och tvinga *alla*
id-/sökvägsparametrar genom den (`_safe_vault_path` + `validate_item_id`).
Detta stänger hela klassen av traversal-buggar på ett ställe.

## 2. Aktivera `aud`-verifiering och lås DCR

**Problem.** `HydraTokenVerifier` avkodade JWT med `verify_aud=False`. En token
utfärdad för en *annan* audience/resurs accepterades så länge signatur och
issuer stämde. Med öppen dynamisk klientregistrering (`OIDC_DYNAMIC_CLIENT_
REGISTRATION_ENABLED: "true"`) öppnar det för confused-deputy.

**Åtgärd.** Verifiera `aud` mot `resource_server_url` (båda trailing-slash-
varianterna, precis som DCR-proxyn redan injicerar). Nästa steg: kräv
`initial_access_token` eller stäng öppen DCR i produktion.

## 3. Gör CI till ett riktigt skyddsnät

**Problem.** `.github/workflows/ci.yml` kör bara `py_compile` + docs-check;
testkörningen är en `TODO`. Därför hade två tester tystnat sönder utan att
någon märkte det.

**Åtgärd (gjort).** `checks`-jobbet installerar nu `gateway[dev]` och kör
`pytest` som hård gate, kompilerar hela paketet (`compileall`) och behåller
docs-index-checken. `pyjwt` — som importerades av `auth/token.py` men saknades
i beroendena — är tillagt i `pyproject.toml`. Kvar: `ruff`/`mypy`/`bandit` som
separata steg.

## 4. Riktig fleranvändar-auth + ACL på board:en

**Problem (två delar).** (a) `MEMAIX_LOGIN_PASSWORD_HASH` är *en* hash — alla
tillåtna användarnamn delar samma lösenord. (b) `api_item_patch` tillät
statusändring för alla med projektet i `visible_projects` (även `reader`),
medan MCP-verktyget `backlog_set_status` kräver `owner`. Board:en kringgick
alltså behörighetsmodellen.

**Åtgärd.** Board-PATCH går nu genom `acl.enforce(user, project, "owner")`
(authz-glappet är stängt). Kvar att göra: per-användare-hash eller återanvänd
Hydra-sessionen istället för egen delad-lösenord-cookie.

## 5. Enhetlig behörighets-/audit-dekorator

**Problem.** `server.py` upprepar `_user()` → `_rl()` → `_audited()` i ~40
verktyg. Det är lätt att glömma ett steg (t.ex. gör `calendar_*` `enforce` i
två lager, andra i ett).

**Åtgärd (gjort).** `server.py` har nu en `_tool_call(tool, project, fn, *tail,
need=None)`-hjälpare som centralt gör identitet + rate-limit + valfri ACL-enforce
+ audit och anropar `fn(acl, user, project, *tail)`. Alla files/memory/backlog/
pm/email-verktyg går genom den, vilket tog bort ~3 rader boilerplate per verktyg
och gör steg-glömska omöjlig. Verktygssignaturerna (och därmed FastMCP-schemana)
är oförändrade. Nya smoke-tester i `test_server.py` täcker vägen.

## 6. Flytta delat tillstånd till en backend

**Problem.** Rate-limiter, OAuth-`_pending_states` och den efemära
`TOKEN_MASTER_KEY`-fallbacken är alla process-lokala — de går sönder så fort du
kör fler än en uvicorn-worker.

**Åtgärd (gjort).** `SQLiteRateLimiter` (samma gränssnitt som den in-memory-
baserade) väljs via `MEMAIX_RATELIMIT_BACKEND=sqlite` + `MEMAIX_RATELIMIT_DB`.
OAuth-pending-states persisteras i SQLite när `MEMAIX_STATE_DB` är satt, så
callbacken kan hanteras av en annan worker. `TOKEN_MASTER_KEY` är nu obligatorisk
i HTTP-läge (annars vägrar gatewayen starta) om inte `MEMAIX_ALLOW_EPHEMERAL_KEY=1`
sätts explicit. Default-beteendet (in-memory) är oförändrat. Nästa steg för riktig
hög skala: en Redis-backend bakom samma gränssnitt.

## 7. Robust OAuth-konto-identitet

**Problem.** `_get_account_email` läser `token_data["email"]`, men Googles
token-svar innehåller ingen `email` (den ligger i `id_token`). Alla Google-
konton lagras därför under nyckeln `linked-google` → ett andra konto skriver
över det första, och `account_list` visar platshållaren.

**Åtgärd (gjort).** `server._get_account_email` avkodar nu `id_token`s claims
(utan signaturverifiering — token kom redan direkt från providerns token-endpoint
över TLS) och använder `email`/`preferred_username`/`upn`, med `sub` som andra
fallback. Två länkade Google-konton kolliderar inte längre under samma nyckel.
`memaix.example.yaml` uppdaterad med `openid`+`email`-scopes så providern
faktiskt skickar med det. `needs_relink`-signalen vid refresh-fel fanns redan
(`mark_needs_relink`).

## 8. Härda alla externa I/O-anrop

**Problem.** `email_search` byggde `mb.fetch(f'BODY "{query}"')` — en `"` i
query kunde bryta ut ur söksträngen (IMAP-injektion). `memory_revert` skickade
`commit` direkt till `git revert` utan `--`-guard (argumentinjektion). Externa
anrop (Google, Hydra, iCal) saknar på flera ställen felisolering.

**Åtgärd.** IMAP-query escape:as nu, git-kommandon har `--`-guard och
commit-validering. Kvar: konsekventa `timeout` + retry/backoff runt alla
`requests`/`httpx`-anrop.

## 9. Strukturerad, säker loggning + observability

**Problem.** `server.py:868` anropade `logger.warning(...)` men `logger` var
aldrig definierad — felgrenen kastade `NameError`. Ingen korrelations-id, ingen
`/metrics`.

**Åtgärd.** Modul-logger införd (fixar `NameError`). Kvar: korrelations-id per
request, `/metrics`-endpoint, och en check att `config.secret()`-värden och
`audit.detail` aldrig loggas i klartext.

## 10. Robust datamodell för backlog/PM

**Problem.** Frontmatter parsas med samma regex på fyra ställen (`backlog.py`,
`board/store.py`, `pm.py`) med olika felhantering. Skrivningar är inte atomiska,
och board-PATCH saknar optimistisk låsning.

**Åtgärd (gjort).** Ny `frontmatter.py` (`split` / `join` / `write_atomic`)
används nu av `backlog.py`, `board/store.py` och `pm.py` — en parser att granska
istället för fyra, och alla skrivningar går via temp-fil + `os.replace` (crash-
säkra). Kvar: pydantic-schema för items och optimistisk låsning även på
board-PATCH (MCP-verktygen har den redan).
