# Säkerhets- och kvalitetsgranskning 2026-07-25

**Omfattning:** 213 `.py`-filer, 31 712 rader Python, 71 dokument.
**Metod:** tre parallella djupdykningar (auth/ACL, injektion/SSRF/LLM, kodkvalitet/tester) plus
genomgång av drift, beroenden och hemligheter. Samtliga KRITISK-fynd verifierade i koden.

## Kortversion

Kärnan är ovanligt gediget byggd. JWT-verifiering, path traversal, SQL, XSS och
secret-hantering är korrekt gjorda, ofta med kommentarer som visar att någon förstått attacken.
Två tidigare säkerhetsrundor syns i historiken.

Det som återstår ligger i **OAuth-consent-steget**, i **SSRF-guardens redirect-blindhet**, och
i att **all persistent state ligger i `/tmp`**.

---

## 1. Arkitektur

```
AI-klient (Claude/ChatGPT, desktop+mobil)
   │ HTTPS, Streamable-HTTP MCP + OAuth 2.1/PKCE
   ▼
cloudflared ──► Caddy :80 (TLS termineras i tunneln)
   │              ├─ /oauth2/register  → gateway (injicerar audience) → Hydra
   │              ├─ /oauth2/*         → Hydra :4444
   │              ├─ /login, /consent  → login-app :3000 ──► Hydra admin :4445
   │              └─ allt annat        → gateway :8080
   ▼
gateway :8080
   ├─ auth/token.py   JWT-verifiering mot Hydras JWKS (aud/iss/exp)
   ├─ acl.py          RBAC: user → grants{projekt: roll}
   ├─ tools/*         email/calendar/files/memory/backlog/pm  (IMAP/CalDAV/WebDAV)
   ├─ outbox/*        grind för utgående åtgärder
   ├─ llm/*           egen agentloop (Fas 2, ej inkopplad)
   └─ web/, board/    webb-UI, egen cookie-session (HMAC)
   ▼
./vaults/<projekt>/  markdown + git (historik) + .memaix.db (SQLite, aktivt tillstånd)
```

`vault-template/` är seed-innehåll som kopieras in i nya projekt-vaults — **prompt-material,
inte kod**. Alla portar bundna till `127.0.0.1`; tunneln är enda publika ytan. Single-tenant per
deployment, konsekvent genomfört.

**Två auth-världar.** MCP-ytan använder Hydra-JWT; webb-UI:t och boarden använder en egen
HMAC-signerad cookie (`memaix_board`). De delar nyckel (`HYDRA_SYSTEM_SECRET`) men inte
livscykel — vilket är roten till flera fynd nedan.

---

## 2. Säkerhet

### KRITISK

#### S1 — SSRF-guarden följer inte med genom redirects ✅ ÅTGÄRDAD

`tools/calendar.py:166-167`, `notify/channels.py:75-80` och `:99-100`.

```python
validate_external_url(self._url)          # kollar URL:en
r = requests.get(self._url, timeout=10)   # requests följer redirects by default
```

*Exploatering:* `calendar_setup(mode="ical_secret", ical_url="https://angripare.example/cal.ics")`.
Publik värd → godkänns. Angriparens server svarar
`302 Location: http://169.254.169.254/latest/meta-data/iam/security-credentials/`.
Gatewayen hämtar molnets instans-credentials. Webhook-kanalen kan använda `307` som bevarar
POST-body → godtycklig JSON mot interna tjänster.

**Förbisett, inte accepterat:** `safety/net.py` resonerar utförligt om DNS-rebinding och TOCTOU
men nämner aldrig redirects. `llm/client.py:151` är enda stället som sätter
`follow_redirects=False`.

**Åtgärdad** i PR #25: `allow_redirects=False` på alla tre, `net.py`-docstring utökad med
"CALLERS MUST DISABLE REDIRECTS", två regressionstester.

#### S2 — Tyst auto-consent + öppen DCR ⇒ kontokapning via en länk

`login-app/app.py:170-215` — `/consent` är en GET som auto-godkänner **allt**, utan
användarinteraktion, utan `client_id`-allowlist, utan `redirect_uri`-kontroll:

```python
{"grant_scope": requested_scope,
 "grant_access_token_audience": audience,   # ← från angriparens ?resource=
 "remember": True, "remember_for": 86400 * 30}
```

Kombinerat med `login-app/app.py:119-125` (auto-accept när Hydra minns sessionen, 30 dagar) och
`server.py:2510` + `docker-compose.yml:96` (oautentiserad DCR).

*Exploatering:* angriparen POSTar en egen klient till `/oauth2/register` (ingen auth). Offret
öppnar en länk till
`/oauth2/auth?client_id=<angripare>&redirect_uri=<angripare>&resource=https://mcp.example.com`.
Offrets 30-dagarssession → `skip`-grenen accepterar login utan formulär → consent beviljar alla
scopes och angriparens audience → auth code till angriparen.
**PKCE hjälper inte — angriparen är klienten.**

Öppen DCR krävs av MCP-specen för claude.ai. **Det fixbara är consent-steget:** riktig
consent-sida för icke-förregistrerade klienter, eller auto-consent enbart mot en
`client_id`-allowlist.

### HÖG

#### S3 — All persistent state ligger i containerns `/tmp`

`docker-compose.yml:10-16` monterar bara `./config` och `./vaults`. Ingen av de 14
`MEMAIX_*_DB`-variablerna sätts, och defaults (`server.py:119,127,136,145,307…`,
`outbox/queue.py:176`, `safety/rate_limit.py:152`) pekar alla på `/tmp/memaix-*.db`.

Vid varje omstart försvinner: **revisionsloggen, utkorgskön, undo-tidslinjen, sökindexet,
rate-limitern, LLM-budgettaket och OAuth-tokenlagret.** `restart: unless-stopped` gör omstarter
rutin.

Forensiskt allvarligt: `SECURITY.md` lutar sig på revisionsloggen som kompenserande kontroll för
egress. `agent.py:64-66` säger själv i en docstring att *"ett kostnadstak som nollställs av en
deploy är inget tak"* — och nollställs sedan av varje deploy.

#### S4 — MFA kan kringgås genom att bara enrolla om sig

`web/api/mfa.py:134-194`. `setup_start`/`setup_confirm` kräver bara `_require_user` + `is_admin`
— ingen kontroll av att användaren *inte redan* är enrollad, ingen befintlig MFA-cookie. Rad 185
skriver rakt över befintlig secret. Den som har admin-cookien (ett faktor: lösenord) begär ny
secret i klartext, räknar fram koden, enrollar om sig → 8 h MFA-cookie → hela `admin_write.py`
öppen. **MFA blir aldrig ett *andra* faktor.**

#### S5 — Kill-switchen gäller inte webbsessionen

`acl.enforce` fail-closar korrekt på `disabled` (`acl.py:63-64`), men **ingen webbyta går via
`enforce`**: `board/routes.py:98-120` kollar bara HMAC + env-allowlist; `web/api/admin.py:34`
och `admin_write.py:37` använder `is_admin()` som inte tittar på `disabled`; `acl.py:82-85`
`visible_projects` likaså. En avstängd admin behåller cookien i upp till 2 dygn och kan sätta
`disabled: false` på sig själv igen.

#### S6 — Ingen brute-force-spärr på något lösenordslogin

`login-app/app.py:134-147` och `board/routes.py:169-190` — inget rate limit, ingen lockout
(jfr `mfa.py:112-113` som *har* 5/10 min). Dubbel konsekvens: obegränsad gissning, **och** varje
oautentiserad request kostar `pbkdf2_hmac(…, 200_000)` → några parallella klienter slår ut
gatewayen.

#### S7 — Agenten kan självgodkänna sin egen utkorg (latent)

`llm/toolbridge.py:29`: `_NEVER_FOR_CHAT = frozenset()` — tom. `capabilities/catalog.py:294-300`
exponerar `outbox_approve`/`outbox_reject` på `reader`-nivå. Utkorgen är designad som *mänsklig*
grind, men agenten kör som användaren och inget skiljer "människan klickade Godkänn" från
"modellen anropade verktyget". Ett prompt-injicerat mejl kan be agenten köa `email_send` och
sedan godkänna det själv.

**Latent:** `run_turn` har idag ingen produktionsanropare (endast tester). Men maskineriet står
färdigt. **Fix innan Fas 3: en rad.**

#### S8 — `.env` skrivs världsläsbar i install-flödet

`scripts/bootstrap.py:330-342` (`ensure_secrets`) skriver `.env` med `ENV.write_text()` och
**anropar aldrig chmod** — trots att `bootstrap.py:278` skriver ut *"(.env: hemligheter
genererade, chmod 600)"*. Verifierat empiriskt: resultatet blir `0644`. Filen innehåller
`HYDRA_SYSTEM_SECRET` och `TOKEN_MASTER_KEY`.

Wizard-vägen (`setup_engine.py:195`) gör rätt — det är `make install`-vägen som läcker.

#### S9 — Hydra kör i dev-läge med hemlighetsläckande loggar

`docker-compose.yml:86` `serve all --dev` (avaktiverar HTTPS-krav), `:93` `LOG_LEVEL: debug`,
`:94` `LOG_LEAK_SENSITIVE_VALUES: "true"` — tokens och secrets i klartext i containerloggarna.
**Detta är produktionscompose-filen.**

### MEDEL

- **S10 — Webhook-rate-limiten är global.** `server.py:2448-2450` nycklar på
  `request.client.host`, som bakom Caddy alltid är proxyns container-IP. Alla delar en bucket på
  30/60 s → en angripare kan spärra ute alla legitima webhooks.
- **S11 — ReDoS i regelmotorn.** `rules/match.py:67-68` kör användarens regex mot angriparstyrd
  mejl-/webhook-input utan längdtak eller timeout, synkront i webhook-routen.
- **S12 — Utkorgens default är `auto`.** `outbox/policy.py:78-81`. Känt och dokumenterat, men
  värre än det ser ut: `rules/actions.py:63` kopplar `email_send` till regelmotorn med
  `event["payload"]` från *oautentiserat webhook-innehåll* — en autonom egress-väg utan LLM.
- **S13 — Ingen domänseparation mellan board- och MFA-cookiens signatur.**
  `board/routes.py:92-95` vs `mfa.py:63-69` signerar samma payload-form med samma nyckel.
  Räddas idag *bara* av att board använder dagnummer och MFA unix-tid. Byter någon enhet blir
  "har session" = "MFA-verifierad".
- **S14 — Board-sessionen kan inte återkallas**, lever 24–48 h (`abs()` accepterar en dag
  framåt), inget session-id → lösenordsbyte ogiltigförklarar inget.
- **S15 — Inget CSRF-skydd**, allt vilar på `samesite="lax"`. Login-CSRF fungerar:
  `board/routes.py:171` läser JSON utan content-type-kontroll.
- **S16 — Hydras admin-API (`:4445`) är oautentiserat** och nåbart från varje container i
  compose-nätverket.

### LÅG
Timing-baserad användarenumerering (`login-app/app.py:142`) · `acl.yaml` med lösenordshashar
skrivs med default-umask (`setup_engine.py:160-172`) · YAML-injektion via ovaliderad `domain`
(`setup_engine.py:119-146`) · signeringsnyckeln paddas i stället för avvisas
(`board/routes.py:66`) · `memory_history` saknar `_validate_note_path` (`tools/memory.py:117-128`)
· oescapad exception i HTML (`login-app/app.py:116,160,181`) · latent XSS-footgun i `app.js:46`.

### Hemligheter — rent
Ingen incheckad nyckel, varken i arbetsträdet eller i git-historiken (pickaxe-sökt). `.gitignore`
täcker `.env`, `config/*.yaml`, `cloudflared/*`. `config.secret()` löser `env:`/`file:`-referenser,
aldrig värden i YAML. Alla `logger`/`print` grepade mot key/token/secret/password: **noll läckor**.

### Beroenden
`gateway/pyproject.toml:7-22` — i princip **allt är opinnat** (`mcp`, `httpx`, `pyyaml`,
`requests`…), `login-app/requirements.txt` helt opinnat, inga hashar. Det motsäger direkt
`SECURITY.md`:s eget krav ("Pinna beroenden — versioner + hashar"). Mildrande: CI kör
`pip-audit --strict` på varje PR och genererar SBOM. Ingen känd sårbar version identifierad —
men bygget är inte reproducerbart.

---

## 3. Kodkvalitet

**Filer >500 rader:** `server.py` **2634**, `tools/calendar.py` 644, `pm/store.py` 559,
`board/routes.py` 529, `tests/test_server.py` 587, `scripts/bootstrap.py` 534.

`server.py` är den enda filen i paketet som inte får betyg A — maintainability index **4.68 (C)**,
mot A/28 för näst sämsta. 156 funktioner, 91 verktygsregistreringar, HTTP-app-bygge,
OAuth-token-refresh och kalender-backend-resolution i samma fil. `build_http_app`
(`server.py:2191`) är **387 rader**.

**Cyklomatisk komplexitet** (radon, snitt A/3.12 över 971 block — tailen är problemet):

| CC | Plats |
|---|---|
| 40 (E) | `notify/brief.py:31` `build` |
| 37 (E) | `pm/allocate_cpsat.py:51` |
| 36 (E) | `pm/allocate.py:89` |
| 26 (D) | `server.py:2106` `_resolve_calendar_dav` |
| 25 (D) | `search/query.py:86` `search_all` |

**Breda except:** 96 handlers, **19 sväljer helt**. Sju av dessa är **audit-loggskrivningar på
egress-vägar** — `outbox_execute` (`board/routes.py:506` *och* `web/api/outbox.py:111`,
byte-identisk copy-paste), `outbox_reject` (`:489`), LLM-verktygsdispatch
(`llm/toolbridge.py:144`), automationsregler (`rules/actions.py:48`, vars docstring ordagrant
säger att vägen annars *"vore osynlig i revisionsloggen"* — och sedan sväljer felet som gör den
osynlig).

Policyn är medveten och dokumenterad i bandit-konfigen, men det finns **ingen
degraderad-läge-signal**: en trasig audit-backend är oskiljbar från ett tomt system.
Fix: behåll `pass`, lägg till en `logger.warning` — sju rader.

**Duplicering:** **12 handrullade SQLite-store-klasser** delar ett identiskt 8-radersblock
(`outbox/queue.py:32`, `pm/store.py:44`, `notify/store.py:23`, `search/store.py:27`,
`rules/store.py:25`, `timeline/store.py:26`, `safety/idempotency.py:40`,
`nextcloud/notes_store.py:26` m.fl.). En basklass som aldrig skrevs — **och den har redan drivit
isär.** Verifierat: `backends/token_store.py` är den enda utan `PRAGMA journal_mode=WAL`.
Det är alltså precis den store som håller OAuth-tokens som saknar durabilitetsinställningen alla
syskon har.

**Mutable default args: noll.** Verifierat med full AST-genomgång.

**Typannoteringar:** 88,9 % returtyper, 84,9 % parametrar, 74,9 % helt annoterade. Värst:
`connectors/catalog.py` med **1 annoterad parameter av 41**. Viktigare: `mypy` är inte strict —
`check_untyped_defs` är av, vilket betyder att de 69 helt oannoterade funktionerna **inte
typkontrolleras alls**.

**Lint:** ruff passerar rent mot vald regeluppsättning (`E,F,W,I`). Utökat till
`B,SIM,UP,C90,ARG,RET,PTH,S` ger 300 fynd — varav **C901 (15) och B904 (5) saknar dokumenterad
motivering**. En komplexitetsgräns är den enda regel som hade fångat tabellen ovan.

---

## 4. Tester

**936 testfunktioner i 88 filer** mot 91 källmoduler — nära 1:1, ovanligt disciplinerat.
`pytest --collect-only` gav **538 tester + 38 collection-fel**; felen är *rent miljömässiga*
(maskinen har Python 3.9.6, projektet kräver ≥3.12; `mcp`/`defusedxml` saknas). CI kör 3.12.
**Noll `skip`/`xfail`** någonstans.

**E2E** (`tests_e2e/`, 21 tester, riktig Chromium): eget CI-jobb, inte skippat — bara exkluderat
från default via `testpaths`. Auktorisationsfokuserad snarare än smoke-test: sju tester är
privilegiegränser (reader ser ingen revert-knapp, outbox synlig för owner men inte reader, admin
nekad för reader), plus MFA-enrollment med riktig TOTP, kill-switch live, open-redirect-guard och
SSRF-avvisning i UI:t. `page`-fixturen failar på JS-`pageerror`, så tyst frontend-brott fångas.

**Otestat:** 10 moduler av 91 saknar direkt test. Två spelar roll — **`paths.py` (65 rader)** och
**`frontmatter.py` (68 rader)**, dvs. path-hantering och frontmatter-parsning: klassiska
traversal-/injektionsytor, noll direkta tester. (Path-logiken är korrekt skriven — bara inte
testad direkt.)

**Strukturell lucka i RBAC-testningen:** ACL-enforcement är **inte centraliserad**. `_tool_call`
(`server.py:528-547`) kör `acl.enforce` bara när `need` skickas explicit — vilket ingen av de
~60 registreringarna gör. Kontraktet är att varje verktyg själv anropar `enforce` först. Alla
nuvarande verktyg gör det (verifierat), men **inget hindrar att ett nytt glömmer**.

---

## 5. Drift

`install.sh` → `make init` → `scripts/bootstrap.py`; alternativt `setup.sh` → webbwizard på
`127.0.0.1:8765` med engångstoken.

**Wizarden är repots bäst härdade del:** 128-bitars token, `hmac.compare_digest`,
localhost-bindning, vägrar starta om `config/acl.yaml` finns, stänger av sig själv efter
skrivning, CSP + `X-Frame-Options: DENY`, hemligheter ekas aldrig tillbaka.

**Hälsokontroller:** `/health` finns (`server.py:2508`), `doctor`-kommando finns, och
`ops/memaix-watchdog.{service,timer}` kör en väktare var 6:e timme som verifierar gateway, Hydra,
publik URL genom CDN, frontend-hash och skrivbarhet — med självläkning via
`docker compose restart`, en gång. Genomtänkt.

**Men:** `docker-compose.yml` har **noll `healthcheck:`-block**. `depends_on: condition:
service_started` är därför meningslöst. Båda Dockerfiles saknar `USER`-direktiv →
**containrarna kör som root**.

**Dokumentationsdrift:** `gateway/README.md` beskriver fortfarande `server.py` som `[stub]`,
`auth/` som `[todo]` och `tools/` som `[stub]` — alla tre är byggda och omfattande. Bryter mot
projektets egen `AGENTS.md §6b` regel 3. Två filer saknar SPDX-header (118/120 har den):
`scripts/gen-password-hash.py` och `gateway/src/memaix_gateway/board/__init__.py`.
---

## Vad som faktiskt är rätt gjort

Värt att säga rakt ut, för det är ovanligt:

**JWT-verifieringen är på riktigt** — `auth/token.py:47-62` hämtar nyckeln från JWKS, sätter
`algorithms=["RS256","ES256"]`, verifierar iss, aud och exp, och stänger aldrig av
signaturkontrollen i auth-vägen.

**Path traversal är stängt** via ett centraliserat `paths.py` med tre lager, och projektväljaren
är inte traverserbar — `project` är ren nyckeluppslagning i `acl.projects`.

**Noll träffar på de klassiska farliga anropen.** Ingen dynamisk kodexekvering, ingen osäker
deserialisering, inga skalanrop med interpolerade argument, och YAML läses genomgående med den
säkra laddaren.

**All SQL är parametriserad** — sju f-strängar i SQL-kontext, alla interpolerar bara
`?,?,?`-platshållare, alla med motiverande `# nosec`.

**XSS:** webb-UI:t renderar via `createElement`/`textContent` genomgående, inklusive en
markdown-renderare byggd helt på DOM-noder.

**Argument-injektion:** `memory_store.py:234-236` avvisar allt som inte är ren git-hash före
`git revert`, med kommentar om att `-x` annars tolkas som flagga — den attacken missar de flesta.

`safety/net.py` blockerar korrekt IPv4-mappad IPv6, NAT64, ULA, oktal- och decimalkodade IP samt
userinfo-tricket. Lösenord: PBKDF2-SHA256, 200k iterationer, slumpsalt, konstanttidsjämförelse.
Utkorgen är approver-scopad end-to-end via en enda sanningskälla.

---

## Prioriterad åtgärdslista

1. ~~`allow_redirects=False` på tre rader (S1)~~ — **åtgärdad, PR #25**
2. **Consent-allowlist eller riktig consent-sida (S2)** — den enda som kräver design
3. **Volym för `/data` + sätt alla `MEMAIX_*_DB` i compose (S3)**
4. `_NEVER_FOR_CHAT = frozenset({"outbox_approve", "outbox_reject"})` (S7) — innan Fas 3 gör den
   nåbar
5. Ta bort `--dev` och `LOG_LEAK_SENSITIVE_VALUES` ur Hydra (S9); `chmod 0600` i
   `ensure_secrets` (S8)
6. Kräv befintlig faktor vid MFA-omenrollning (S4); låt `is_admin`/`visible_projects` respektera
   `disabled` (S5); rate-limita båda loginvägarna (S6)
7. Billigast med störst effekt på kodkvalitet: `C901` + `B904` i ruff `select`, och
   `check_untyped_defs = true` i mypy

## Åtgärdat i samma omgång

| Fynd | PR |
|---|---|
| S1 — SSRF genom redirects | [#25](https://github.com/Quinzell-se/memaix/pull/25) |
| `acl.py:51` admin-flaggan accepterade truthy-värden | [#23](https://github.com/Quinzell-se/memaix/pull/23) |
| `docs/ARCHITECTURE.md` dokumenterade ~30 av 91 verktyg | [#24](https://github.com/Quinzell-se/memaix/pull/24) |
