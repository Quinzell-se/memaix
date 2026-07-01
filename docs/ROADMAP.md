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
- 📋 **#5 Ångra & tidslinje** — [FEATURE-UNDO-TIMELINE.md](FEATURE-UNDO-TIMELINE.md)
- ✅ **#6-L0 Förmåge-register + coverage-test** — [FEATURE-DISCOVERABILITY.md](FEATURE-DISCOVERABILITY.md) (L1–L3 kvarstår)
- ✅ **kod #7 OAuth-konto-identitet** (riktig e-post) — [DEVELOPMENT-PROPOSALS.md](DEVELOPMENT-PROPOSALS.md) §7

**Varför nu:** utkorg + ångra gör autonomin trygg; registret är billigt och allt
efteråt registrerar sig i det (annars faller coverage-testet); riktig konto-
identitet krävs för per-user mail/kalender.
**DoD:** utgående åtgärder kan gate:as och godkännas; skrivande åtgärder kan ångras;
varje MCP-verktyg är täckt av registret; flera Google-konton kan samexistera.

## Fas 2 — Minne & intelligens 📋
- 📋 **#2 Semantisk sökning / RAG** — [FEATURE-SEMANTIC-SEARCH.md](FEATURE-SEMANTIC-SEARCH.md)

**Varför nu:** retrieval-lagret återanvänds av brief, PM-agent och upptäckbarhet —
störst hävstång. Bara `frontmatter` (klart) som beroende.
**DoD:** ACL-styrd hybrid-sökning (FTS5 + vektor) med källhänvisning; hooks håller
indexet färskt; degraderar till FTS5 utan embedder.

## Fas 3 — Proaktivitet 📋
- 📋 **#1 Brief + scheduler** — [FEATURE-PROACTIVE-BRIEF.md](FEATURE-PROACTIVE-BRIEF.md)
- 📋 **#4 Automationsregler** — [FEATURE-AUTOMATION-RULES.md](FEATURE-AUTOMATION-RULES.md)
- 📋 **#6-L1/L2/L3 Guide** (tur, `memaix_help`, knuffar) — [FEATURE-DISCOVERABILITY.md](FEATURE-DISCOVERABILITY.md)

**Beroenden:** #1 bygger den generiska schemaläggaren som #4 återanvänder; #4:s
utgående åtgärder går **alltid** via Utkorgen (#3); guiden visar nu riktiga
funktioner. **DoD:** schemalagd brief levereras idempotent via sidokanal; regler
utlöses av schedule/mail/webhook/internal och kör en gång; "vad kan du göra?" ger
överblick → drill-down.

## Fas 4 — Ekosystem & fördjupning 📋
- 📋 **Connector-ramverk** — [FEATURE-CONNECTOR-FRAMEWORK.md](FEATURE-CONNECTOR-FRAMEWORK.md)
  *(realiserar adaptermodellen i [BACKENDS.md](BACKENDS.md) som en pluggbar SDK)*
- 📋 **Nextcloud som förstklassig backend** — [FEATURE-NEXTCLOUD-BACKEND.md](FEATURE-NEXTCLOUD-BACKEND.md)
  *(beror på connector-ramverket)*
- 📋 **PM-planeringsmotor + agent** — [FEATURE-PM-ENGINE.md](FEATURE-PM-ENGINE.md)
  *(bygger [PM-PLANNING-ENGINE.md](PM-PLANNING-ENGINE.md) + [PM-DATA-MODEL.md](PM-DATA-MODEL.md))*

**Varför sist:** störst värde när kärnan är stabil, sökbar och säker. PM-motorn
kan dock byggas parallellt med fas 2–3 eftersom den är fristående.
**DoD:** samma verktyg fungerar över flera backends; Nextcloud Files/Contacts/Talk
är förstklassiga; PM-motorn beräknar schema/kritisk linje/what-if deterministiskt.

---

## Tvärgående (löpande)
- **Kvalitetsgrindar:** `ruff` / `mypy` / `bandit` som CI-steg (DEVELOPMENT-PROPOSALS #3, nästa steg).
- **Skala:** Redis-backend bakom rate-limit/state-gränssnittet när fler workers behövs (#6).
- **Datarobusthet:** pydantic-schema för backlog/PM-items (#10, nästa steg).
- **Tidszoner:** normalisera all tid till UTC, visa i användarens tz (OPEN-GAPS #16) — berör brief, kalender, PM.
- **Idempotens:** idempotensnycklar för alla skrivande verktyg (OPEN-GAPS #13) — delvis löst i #1/#3/#4.

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
