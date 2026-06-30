# Drift-säkerhet — guardrails, concurrency, context, retention

Runtime-skydden som saknades i v1 (efter extern granskning, se REVIEW-RESPONSE.md). Skyddar mot
skenande AI, parallella skrivningar, kontextöverflöd och kvarliggande data.

## 1. Rate limiting
Per **användare**, **projekt** och **verktyg** (glidande fönster). Skyddar backends (IMAP/CalDAV/
WebDAV/API) mot översvämning.
```yaml
limits:
  per_user:    { calls_per_min: 60 }
  per_project: { calls_per_min: 120 }
  per_tool:    { email_send: { calls_per_hour: 20 } }
```
Överskridet → verktyg returnerar `rate_limited` (mjukt fel, AI:n får backa).

## 2. Circuit breakers
Per backend. Upprepade fel (t.ex. IMAP nere) → bryt kretsen, returnera snabbt `backend_unavailable`
istället för att hänga/retrya i loop. Half-open: testa försiktigt efter en paus.

## 3. Budgetar
Per projekt/användare och tidsfönster: **max verktygsanrop** och **max token/kostnad**. Hindrar att
en enda session bränner allt. Vid nått tak → `budget_exhausted` + valfritt `operator_alert`.

## 4. Loop-detektion
Upptäck skenande mönster — identiska anrop i rad, snabb repetition, samma item skrivet om och om.
Vid träff: **stoppa**, logga, larma operatör. Detta är skyddet mot "LLM hallucinerar och spammar
IMAP-servern".

## 5. Concurrency-kontroll
- **Vault-skrivningar serialiseras** per projekt (skrivkö) — inga git-/fil-race.
- **Backlog-items: optimistisk låsning** via `version`-fält. Skriver A och B samtidigt → den andra
  får `conflict` och måste läsa om. Ingen tyst överskrivning.
- Aktivt tillstånd i **SQLite** (transaktioner) gör detta robust; git tar historiken asynkront.

## 6. Context & retrieval (dumpa aldrig)
AI:n får **aldrig** hela inkorgen/mappträdet/10 års trådar i kontexten.
- Alla backends nås via **search + pagination + limit** — aldrig bulk-dump.
- **Index** över minne + filer för relevans: börja med **SQLite-FTS** (gratis, ingen extra infra);
  **vektor-index** först när semantisk sökning verkligen behövs.
- **Sammanfatta** långa trådar/dokument innan de göds in. Spara sammanfattningar i minnet.

## 7. Data retention & GDPR
- **Retention-policy per projekt** (t.ex. rensa minnesnoteringar/loggar äldre än N månader).
- **Purge-rutin:** radera en persons data ur minne + token-store på begäran (rätt att glömmas).
- Retention gäller även audit-logg (enligt policy) och per-användar-OAuth-token vid avlänkning.

## 8. Destruktiva åtgärder kräver bekräftelse
Som `email_send` (utkast-bara) gäller för **alla destruktiva åtgärder**: `email_delete`,
`email_move`, `calendar_delete/cancel`, `files_delete`. Standard: AI:n får **inte** utföra dem utan
**explicit mänsklig bekräftelse**. Skyddar mot att en felresonerande AI raderar viktig data — och
mot juridiskt ansvar. Konfigurerbart per verktyg, default = bekräfta.

## 9. MFA för admin & setup
Setup-UI och admin-åtgärder kräver **MFA** (TOTP/WebAuthn), inte bara engångstoken. En komprometterad
maskin ska inte ge full åtkomst på en faktor.

## 10. Hemligheter får inte hamna i minnet
Användare klistrar lösenord/nycklar i chatten → annars för evigt i git-historik + backup.
- **Secret-scanning vid `memory_write`/`backlog_*`** — avvisa eller maskera detekterade hemligheter
  (API-nycklar, lösenord, tokens) innan de skrivs. Samma kontroll på backup. (OPEN-GAPS #3)

## 11. Idempotens för skrivande åtgärder
AI:n retrear ett anrop (nätverksglapp) → dubbla mejl/kalenderhändelser/items.
- **Idempotensnyckel** på alla skrivande verktyg (`calendar_create`, `email_*`, `backlog_add`,
  `memory_write`, importsteg). Samma nyckel → skapa-en-gång. (OPEN-GAPS #13)

## 12. Ångra (undo)
- **`undo`** backar senaste skrivande verktygsanrop (kalenderhändelse, utkast, fil, minnesnotering).
  Minne/backlog har redan git-revert; lyft det till en enhetlig "ångra senaste"-åtgärd. (OPEN-GAPS #8)

## 13. Omedelbar återkallning
Person slutar / enhet tappas → måste kunna dödas direkt.
- **Kill-switch:** revoke OAuth-token (Hydra) + ta bort grant i `acl.yaml` + invalidera sessioner,
  på ett ställe. Verifieras av doctor (ingen kvarglömd access). (OPEN-GAPS #6)

## 14. Granulär åtkomst *inom* ett projekt
RBAC är per projekt — men en extern konsult ska kanske inte se *hela* inkorgen.
- **Resurs-nivå-grants** (per mapp/etikett/kalender), inte bara per projekt. Default minst-möjligt för
  `collaborator`/externa; ägaren öppnar upp explicit. (OPEN-GAPS #4)

## Audit (lyft till kärna)
Basal audit — vem/vilket verktyg/vilket projekt/vilken resurs, tidsstämplat — är **kärna**, inte
bara enterprise. Enterprise lägger på immutabilitet + SIEM-export (ENTERPRISE.md).

## Kostnad
Allt ovan är **kod, ingen ny infra**. SQLite-FTS och SQLite-tillstånd är filbaserat och gratis.
Vektor-index (om/när) kan bli en lättviktskomponent — deferras tills behovet är bevisat.

## Acceptanskriterier
- [ ] En skenande AI stoppas av rate limit/loop-detektion innan en backend översvämmas.
- [ ] Två samtidiga skrivningar till samma backlog-item ger `conflict`, inte tyst överskrivning.
- [ ] Inget verktyg kan bulk-dumpa en hel mapp/inkorg i kontexten.
- [ ] En persons data kan purgas ur minne + token-store på begäran.
- [ ] Basal audit finns i kärnan, inte bara enterprise.
- [ ] Destruktiva åtgärder (radera/flytta mejl, avboka möte, radera fil) kräver mänsklig bekräftelse.
- [ ] Setup/admin kräver MFA, inte bara engångstoken.
