# Implementeringsroadmap

SPDX-License-Identifier: AGPL-3.0-or-later

Enda källan för *bygg-ordningen*: hur den härdade plattformen, de sex
funktionsspecarna och ekosystem-satsningarna hänger ihop och i vilken följd de
bör byggas. Principen: **gör autonomin säker och agenten självbeskrivande innan
den görs proaktiv**, och bygg retrieval-lagret tidigt eftersom nästan allt annat
lutar sig mot det.

Legend: ✅ klart (i `main`) · 🔨 nästa · 📋 specad, ej byggd.

---

## Beroendegraf (översikt)

```
  Fas 0 Plattform ✅
     │
     ├──► Fas 1 Förtroende: Utkorg(#3) · Ångra(#5) · Förmåge-register(#6-L0) · OAuth-identitet(kod#7)
     │          │
     │          ▼
     ├──► Fas 2 Intelligens: Semantisk sökning/RAG(#2)
     │          │
     │          ▼
     ├──► Fas 3 Proaktivitet: Brief+scheduler(#1) ──► Regler(#4)   ·   Guide(#6-L1/L2/L3)
     │                                   (regler skickar ALLTID via Utkorgen #3)
     │
     └──► Fas 4 Ekosystem: Connector-ramverk ──► Nextcloud-backend
                            PM-planeringsmotor
```

---

## Fas 0 — Plattform & härdning ✅ (i `main`, PR #1–#2)
Grunden att bygga tryggt på.
- Säkerhetsfixar: path traversal, JWT `aud`, board-authz, IMAP/git-injektion, `logger`.
- CI kör testsviten; `_tool_call` (enhetlig identitet/rate-limit/ACL/audit);
  SQLite-backends för rate-limit & OAuth-state; `frontmatter` + atomiska skrivningar.

**DoD:** grön testsvit i CI på varje PR; inga kända öppna säkerhetsfynd.

## Fas 1 — Förtroende-grund 🔨
Gör det säkert att låta agenten göra mer — *innan* den blir proaktiv.
- ✅ **#3 Utkorg** — [FEATURE-APPROVAL-OUTBOX.md](FEATURE-APPROVAL-OUTBOX.md) (backend+MCP+board-API klart; board.html-panel kvarstår)
- ✅ **#5 Ångra & tidslinje** — [FEATURE-UNDO-TIMELINE.md](FEATURE-UNDO-TIMELINE.md) (v1: memory_write/append, calendar_create, backlog_add, board_move; fältnivå-undo för backlog_set_status/score/comment/calendar_update kräver pre-image-fångst och är kvar)
- ✅ **#6-L0 Förmåge-register + coverage-test** — [FEATURE-DISCOVERABILITY.md](FEATURE-DISCOVERABILITY.md) (L1–L3 klart i Fas 3, se nedan)
- ✅ **kod #7 OAuth-konto-identitet** (riktig e-post) — [DEVELOPMENT-PROPOSALS.md](DEVELOPMENT-PROPOSALS.md) §7

**Varför nu:** utkorg + ångra gör autonomin trygg; registret är billigt och allt
efteråt registrerar sig i det (annars faller coverage-testet); riktig konto-
identitet krävs för per-user mail/kalender.
**DoD:** utgående åtgärder kan gate:as och godkännas; skrivande åtgärder kan ångras;
varje MCP-verktyg är täckt av registret; flera Google-konton kan samexistera.

## Fas 2 — Minne & intelligens ✅
- ✅ **#2 Semantisk sökning / RAG** — [FEATURE-SEMANTIC-SEARCH.md](FEATURE-SEMANTIC-SEARCH.md) (hybrid FTS5+vektor, hooks för memory/backlog/files, live mail-fusion; `local`-embedder är valfri extra — `none` ger FTS5-only)

**Varför nu:** retrieval-lagret återanvänds av brief, PM-agent och upptäckbarhet —
störst hävstång. Bara `frontmatter` (klart) som beroende.
**DoD:** ACL-styrd hybrid-sökning (FTS5 + vektor) med källhänvisning; hooks håller
indexet färskt; degraderar till FTS5 utan embedder.

## Fas 3 — Proaktivitet 📋
- ✅ **#1 Brief + scheduler** — [FEATURE-PROACTIVE-BRIEF.md](FEATURE-PROACTIVE-BRIEF.md) (store/kanaler/BriefBuilder/leverans/scheduler/MCP-yta klart; live kalender-fusion i sökningen och FreeBusy/iCal-brief-täckning kvarstår)
- ✅ **#4 Automationsregler** — [FEATURE-AUTOMATION-RULES.md](FEATURE-AUTOMATION-RULES.md) (motor + internal/webhook-triggers + standing instructions klart; live mail-poll och schedule-cron-triggers kvarstår — `rule_test` täcker dry-run för alla triggertyper under tiden)
- ✅ **#6-L1/L2/L3 Guide** (tur, `memaix_help`, knuffar) — [FEATURE-DISCOVERABILITY.md](FEATURE-DISCOVERABILITY.md) (`build_tour` i onboarding, `capabilities`/`memaix_help`/`memaix://capabilities`, `next_suggestion`-knuffar klart; board-panelen (§8) är ren frontend-polish och kvarstår, som outkorgens board.html-panel)

**Beroenden:** #1 bygger den generiska schemaläggaren som #4 återanvänder; #4:s
utgående åtgärder går **alltid** via Utkorgen (#3); guiden visar nu riktiga
funktioner. **DoD:** schemalagd brief levereras idempotent via sidokanal; regler
utlöses av schedule/mail/webhook/internal och kör en gång; "vad kan du göra?" ger
överblick → drill-down.

## Fas 4 — Ekosystem & fördjupning 📋
- ✅ **Connector-ramverk (grund)** — [FEATURE-CONNECTOR-FRAMEWORK.md](FEATURE-CONNECTOR-FRAMEWORK.md)
  *(realiserar adaptermodellen i [BACKENDS.md](BACKENDS.md) som en pluggbar SDK)*
  `connectors/base.py` (kapabilitets-protokoll) + `connectors/registry.py`
  (`ConnectorSpec`/`ConnectorRegistry.get` med `shared`/`per_user`-auth) +
  `connectors/catalog.py` (registrerar dagens `imap`/`caldav`) klart och
  testat isolerat. **Kvar:** flytta `email_*`/`calendar_*`/`files_*`:s
  faktiska anrop till att gå via registret (byter ut `_make_mailbox`/
  `_resolve_calendar_dav`) — skjutet upp eftersom `_resolve_calendar_dav`
  har flera fungerande, testade auth-grenar (OAuth-refresh/iCal/FreeBusy/
  statisk CalDAV) som förtjänar en egen fokuserad migrering; samt en första
  ny extern adapter (Microsoft Graph) som bevis på pluggbarhet.
- 🔨 **Nextcloud som förstklassig backend** — [FEATURE-NEXTCLOUD-BACKEND.md](FEATURE-NEXTCLOUD-BACKEND.md)
  *(beror på connector-ramverket)* — ✅ **Contacts (CardDAV)**:
  `connectors/adapters/contacts_carddav.py` + `contacts_search`/`contacts_get`.
  ✅ **Files (WebDAV)**: `connectors/adapters/files_webdav.py` (PROPFIND/GET/PUT,
  path-traversal blockerad via `paths.validate_relative_path`) + nya
  `nc_files_list/read/write/search`-verktyg + indexeringshook (`nc_files_write` →
  sökbar via `search_all` under en egen `source_type='nc_file'`, skild från lokala
  `file` så källhänvisningen alltid visar rätt backend). Medveten designbeslut: en
  **egen** `files:`-resurs i acl.yaml, inte samma som `vault:` — vaulten är en ren
  sökväg-sträng som hela kodbasen (minne/backlog/PM/onboarding/...) redan förutsätter,
  medan Nextcloud-filer är en *tillkommande* källa nås via nya verktyg, aldrig genom
  att koppla om `files_*`. ✅ **Tasks (CalDAV VTODO)**: `connectors/adapters/
  tasks_caldav.py` (samma PROPFIND+vobject-mönster som Contacts/Files) +
  `nc_tasks_list/add/complete`. Egen `tasks:`-resurs, skild från `calendar:`
  trots att båda defaultar till `type: caldav` — en uppgiftslista och en
  händelsekalender är oftast olika CalDAV-collections. *Nedprioriterat på
  användarens begäran:* Talk (notiskanal). ✅ **Deck-synk**: `connectors/
  adapters/deck_nextcloud.py` (Decks JSON-REST-API, inte ett öppet DAV-
  protokoll) + `nextcloud/sync.py::deck_sync` — nya Deck-kort blir backlog-
  items (id-koppling `deck_card_id` i frontmatter); drift sedan senaste synk
  (`deck_synced_at`-baslinje) upptäcks per sida; ändrar bara en sida vinner
  den sidan, ändrar båda blir det en **konflikt** som loggas och löses med
  "senast ändrad vinner". v1 synkar bara titel+beskrivning (inte etiketter/
  förfallodatum/tilldelning — en uttalad avgränsning). ✅ **Notes-synk**:
  `connectors/adapters/notes_nextcloud.py` (samma JSON-REST-mönster som Deck)
  + `nextcloud/sync.py::notes_sync` — samma konfliktregel som Deck-synken,
  men eftersom minnesanteckningar (till skillnad från backlog-items) saknar
  frontmatter/metadata-plats lever länken+baslinjen i en egen liten
  `NotesLinkStore` (SQLite) istället för i filen själv. Nya Nextcloud-
  anteckningar blir `notes/<slug>.md`. **Kvar:** dokumentgenerering.
- 🔨 **PM-planeringsmotor + agent** — [FEATURE-PM-ENGINE.md](FEATURE-PM-ENGINE.md)
  *(bygger [PM-PLANNING-ENGINE.md](PM-PLANNING-ENGINE.md) + [PM-DATA-MODEL.md](PM-DATA-MODEL.md))* —
  ✅ **Kärnmotorn (steg 1–3) + MCP-yta**: `pm/store.py` (fullt schema från
  PM-DATA-MODEL.md, cykel-avvisning på `dependency`), `pm/schedule.py`
  (kritisk linje: forward/backward pass, FS/SS/FF/SF + lag, cykel → tydligt
  fel), `pm/allocate.py` (prioritetsbaserad list-scheduling: kompetens +
  kapacitet + tillgänglighet + beroenden, deterministisk och idempotent),
  `pm/report.py` (`utilization`, `variance`). Verktyg:
  `resource_add/list/availability/set_skill`, `milestone_add`, `task_add/
  estimate/log_actual`, `dependency_add`, `scenario_add/list`,
  `pm_allocate`, `pm_utilization`, `pm_variance`, `plan_commit` — RBAC per
  PM-AGENT.md (planändring = owner). **Medvetet bortvalt v1:** `task_assign`
  (schemat har inget fält för manuell override — allokering är alltid
  motor-beräknad, matchar "LLM:en räknar aldrig"); kalender är
  arbetsdag-agnostisk (ingen helg/röd dag-modell ännu).
  ✅ **What-if-scenarier**: `pm/whatif.py::whatif` + verktyget `pm_whatif`
  (collaborator, eftersom den aldrig rör den committade planen) — klonar
  bas-scenariot till ett nytt `kind='whatif'`, lägger ändringarna som
  `scenario_change`-rader (samma overlay `allocate.py` redan läser: uppgifts-
  estimat/prioritet/kompetenskrav, resurs på/av), kör om motorn på klonen,
  och diffar resultatet mot bas-scenariots *redan lagrade* schema/allokering
  — rör alltså aldrig bas-scenariot. Diffen pekar ut ändrad slutdatum/
  kritiskhet per uppgift, ändrad resurstilldelning, och förskjutna
  milstolpar. Detta är den kontrollerade "vad händer om"-vägen — i
  kontrast mot att redigera schemat direkt för hand, vilket fortfarande
  inte går (se ovan). **Kvar:** CP-SAT-allokering (uttryckligen valfritt i
  byggspecen), agent-prompter (`pm_plan_session`/`pm_whatif_session`),
  generisk `pm_report(kind, audience)`.

**Varför sist:** störst värde när kärnan är stabil, sökbar och säker. PM-motorn
kan dock byggas parallellt med fas 2–3 eftersom den är fristående.
**DoD:** samma verktyg fungerar över flera backends; Nextcloud Files/Contacts/Talk
är förstklassiga; PM-motorn beräknar schema/kritisk linje/what-if deterministiskt.

---

## Tvärgående (löpande)
- ✅ **Kvalitetsgrindar:** `ruff` / `mypy` / `bandit` som separata CI-gate-steg (DEVELOPMENT-PROPOSALS #3).
  Alla tre körs rent (0 findings) mot hela `gateway/src/memaix_gateway`. Genuina fynd åtgärdades i
  koden (defusedxml för Nextcloud-XML-parsning, None-säkring av SMTP/IMAP-lösenord, explicita
  typannoteringar/asserts för mypy); accepterade-per-design-mönster (best-effort try/except,
  `/tmp`-defaultsökvägar, git-subprocess med listargument, interna invarant-asserts) är
  dokumenterat skippade i `gateway/pyproject.toml`'s `[tool.bandit]`-sektion. De sju SQL-frågor som
  bygger platshållar-antal via f-strängar (alla värden parametriserade) har individuella
  `# nosec B608`-kommentarer med motivering.
- **Skala:** Redis-backend bakom rate-limit/state-gränssnittet när fler workers behövs (#6).
- ✅ **Datarobusthet:** `backlog_schema.py`'s `BacklogItem` validerar varje backlog-items form
  (status-enum, `value`/`complexity`/`risk` 1–5) på läsning och skrivning i `tools/backlog.py`;
  `pm/schemas.py` validerar PM-lagrets skrivmetoder, framför allt `update_task(**fields)` som
  tidigare accepterade vilket fältnamn/värde som helst (`TaskUpdate` med `extra="forbid"` stänger
  det). Board-PATCH fick också valfri `expected_version`-låsning (samma konvention som
  MCP-verktygen) — se DEVELOPMENT-PROPOSALS #10.
- ✅ **Tidszoner:** brief-pipelinen (`notify_prefs.timezone` + `scheduler`/`deliver`/`brief`) var
  redan korrekt tz-medveten per användare, och kalendern litar transparent på tzinfo från
  Google/CalDAV. De faktiska bristerna var `pm/allocate.py`/`pm/report.py`'s fallback till
  server-lokal `date.today()` — bytt till `datetime.now(timezone.utc).date()`; `pm_variance`
  fick även en `today`-override den saknade helt (OPEN-GAPS #16).
- ✅ **Idempotens:** `safety/idempotency.py`'s `IdempotencyStore` cachar resultatet av en lyckad
  körning per (användare, verktyg, idempotency_key) och är inbyggd i `server.py`'s `_audited`-
  knutpunkt — ett upprepat anrop (t.ex. AI:n retrear efter nätverksglapp) returnerar det cachade
  resultatet istället för att upprepa sidoeffekten. Trådat genom `email_send`,
  `email_create_draft`, `calendar_create`, `calendar_update`, `nc_tasks_add` — verktygen med en
  extern, dyr-att-ångra sidoeffekt (OPEN-GAPS #13). Naturligt idempotenta skrivningar
  (överskriv-på-sökväg, uppsert-på-id) och lågrisk-dubbletter (`backlog_add`) behöver ingen nyckel.

## Rekommenderad MVP-lansering
**Fas 0–2 + #1** ger säker autonomi, minne och en morgonbrief — en meningsfull
produkt att släppa. PM-motorn är den skarpaste *differentiatorn* och kan köras som
ett parallellt spår mot samma milstolpe.

## Snabb-referens: alla funktionsspecar
| # | Spec | Fas |
|---|------|-----|
| 1 | [FEATURE-PROACTIVE-BRIEF.md](FEATURE-PROACTIVE-BRIEF.md) | 3 |
| 2 | [FEATURE-SEMANTIC-SEARCH.md](FEATURE-SEMANTIC-SEARCH.md) | 2 |
| 3 | [FEATURE-APPROVAL-OUTBOX.md](FEATURE-APPROVAL-OUTBOX.md) | 1 |
| 4 | [FEATURE-AUTOMATION-RULES.md](FEATURE-AUTOMATION-RULES.md) | 3 |
| 5 | [FEATURE-UNDO-TIMELINE.md](FEATURE-UNDO-TIMELINE.md) | 1 |
| 6 | [FEATURE-DISCOVERABILITY.md](FEATURE-DISCOVERABILITY.md) | 1/3 |
| 7 | [FEATURE-CONNECTOR-FRAMEWORK.md](FEATURE-CONNECTOR-FRAMEWORK.md) | 4 |
| 8 | [FEATURE-NEXTCLOUD-BACKEND.md](FEATURE-NEXTCLOUD-BACKEND.md) | 4 |
| 9 | [FEATURE-PM-ENGINE.md](FEATURE-PM-ENGINE.md) | 4 (parallell) |
