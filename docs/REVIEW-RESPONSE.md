# Svar på extern granskning (v2-justeringar)

Beslutslogg efter en oberoende granskning (extern LLM). Triage: vad vi accepterade, justerade
eller avvisade — och var det åtgärdas. Detta dokument **ändrar** delar av tidigare specar.

## De fyra strategiska forken (beslutade)

| # | Fork | Beslut | Innebörd |
|---|---|---|---|
| 1 | Egen OAuth → beprövad AS | **Ja** | Bygg på **ory Hydra** (cert. OAuth2, DCR). Gateway validerar bara tokens. Tunn login/consent-UI. Tunnel förblir ren proxy (ingen Access → ingen iOS-bugg). |
| 2 | Minnesarkitektur | **Ja** | **SQLite som aktivt tillstånd** + **git async** för historik. Inte commit-per-skrivning i het väg. Löser prestanda + concurrency. |
| 3 | Mejl-reseller | **Ja, justerat** | Skrota mejl-*hosting/reseller* (BYO-infra). **Behåll** projektspecifik mejl-provisionering i kundens egna leverantör för tillfälliga konsulter (se MAIL.md). |
| 4 | Ompositionering | **Nej** | Kärnan kvarstår: gemensam kunskapsbas + dokument + projektledning, AI-agnostiskt. "Kan inte köra Copilot" är en marknadsvinkel, inte identiteten. |

## Accepterade luckor → åtgärdas

| Lucka | Åtgärd | Var |
|---|---|---|
| Ingen rate limiting / circuit breaker / budgetar / loop-skydd | Ny safety-motor | [SAFETY.md](SAFETY.md) |
| Concurrency (två skriver samma item) | Lås/optimistisk versionering | SAFETY.md |
| Context window — får ej dumpa hela mappar/trådar | Retrieval-disciplin + index | SAFETY.md |
| Data retention / GDPR-purge | Retention-policy + purge-rutin | SAFETY.md |

## Partiellt / redan hanterat (granskaren missläste delvis)
- **Deterministisk schemaläggning:** redan vårt val ("matematik i kod, narrativ av AI"). Justering:
  **minska kalender-scope i v1** + strikt tidszonshantering.
- **Audit logging:** finns redan (`features.audit_log`, enterprise-export). Justering: **gör basal
  audit till kärna**, inte bara enterprise.
- **Fleet/IaC:** rätt princip, **stadie-anpassat** — instansen är redan reproducerbar (compose);
  bygg inte 500-instans-orkestrator innан det finns en flotta.

## Kostnadsnotering
Pivoterna är **engineering, inte ny löpande kostnad**. Enda infra-tillägget: Postgres för Hydra
(gratis mjukvara, något större box). SQLite, safety-motor, retention, context-index (SQLite-FTS
först) = ingen ny infra. Projektspecifik mejl = kundens kostnad i deras leverantör. Netto:
**säkrare och billigare**, inte dyrare.

## Andra granskningen (oberoende #2) — konvergens & tillägg

**Konvergens (båda granskarna eniga → hög konfidens, redan i v2):** rate limiting, audit, GDPR/
retention, kapa mejl-reseller, ej hemsnickrad OAuth, git ej som primär-DB. När två oberoende modeller
pekar på samma sak väger det tungt — alla är åtgärdade ovan.

**Avvisat:**
- **Multi-tenant som standard** — motsäger kärnvärdet (kunden äger sin data på egen server) och
  positioneringen Alice bekräftat. Den verkliga oron (drift per kund) möts med **automation**
  (reproducerbar instans + IaC, stadie-anpassat), inte genom att överge isoleringen. Single-tenant kvarstår.
- **"Skjut upp iOS"** — granskaren missläser. Remote MCP-connectorn kör i AI-leverantörens **moln**,
  inte på enheten, så Apples bakgrundsgränser gäller inte. iOS-stöd är verifierat och ett **kärnkrav**.

**Nya accepterade tillägg:**
- **Destruktiva åtgärder kräver bekräftelse** (radera/flytta mejl, avboka möte, radera fil) → SAFETY.md §8.
- **MFA för admin/setup** → SAFETY.md §9.
- **Observability** (monitoring/metrics/health) → planeras som eget spår; knyter till doctor + audit.
- **Juridisk granskning före release** — definiera ansvarsgränser när AI agerar på mejl. Eget spår.
- **Kostnads-/prismodell** — kalkylera driftkostnad + sätt pris (riktvärden att utvärdera:
  self-host gratis, managed-instans ~$50–200/mån eller ~$500–2000/år). Eget affärsspår.
- **AI-kompatibilitets-testmatris** — testa Claude/ChatGPT/Mistral/Perplexity före release (MCP-
  OAuth-mognad är en reell risk).

## Påverkade dokument (uppdaterade)
- `ARCHITECTURE.md` — minne (SQLite+git), auth (Hydra).
- `MAIL.md` — reseller struken; projektspecifik provisionering tillagd.
- `SAFETY.md` — ny: guardrails, concurrency, context, retention.
- `BUILD.md` / `MCP-API.md` — minnes-/auth-semantik följer detta dokument vid bygge.
