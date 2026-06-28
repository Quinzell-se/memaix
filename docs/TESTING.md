# Teststrategi

Utan tester gör Memaix fel **tyst** (OPEN-GAPS #13–14). Särskilt: den deterministiska motorns matematik
*måste* vara bevisat korrekt — den är hela poängen med "matematik i kod, inte LLM".

## Testlager
1. **Deterministiska motorn (kritiskt).** Enhets- + **egenskapstester** för schemaläggning, kritisk
   linje, kapacitet, RCPSP-heuristik, what-if-diff.
   - Känd-svar-fixtures (handräknade scheman).
   - Egenskaper, t.ex.: kritisk linje ≥ varje enskild väg; allokering överskrider aldrig kapacitet;
     cykliska beroenden upptäcks; what-if rör aldrig committed plan.
2. **RBAC-enforcement.** Varje verktyg nekar utan rätt grant; isoleringstest (extern → exakt ett
   projekt; nekas övriga). Detta är säkerhetsgränsen — testa den hårdast.
3. **Idempotens.** Retry av skrivande verktyg ger **inga** dubbletter (samma idempotensnyckel).
4. **Adaptrar.** IMAP/SMTP/CalDAV/WebDAV mot mock/sandbox; fel-/timeout-vägar (circuit breaker).
5. **Säkerhet.** **Prompt-injection-corpus** (THREAT-MODEL.md) — assistenten lyder inte fientligt
   innehåll; secret-scrubbing avvisar hemligheter; egress-allowlist blockerar okänd mottagare.
6. **Eval-svit (LLM, icke-deterministisk).** Verktygsanrop-tillförlitlighet — avgör lokal modell-val
   (LOCAL-MODEL.md). Körs som tröskel (t.ex. ≥ X % korrekta anrop), inte exakt jämförelse.

## CI
- Allt ovan i CI på varje PR. `make docs-check` redan där.
- Container-/image-scanning + beroende-pinning (supply chain, SECURITY.md).

## Acceptanskriterier
- [ ] Motorns matematik har känd-svar- + egenskapstester; CI rött vid regression.
- [ ] RBAC-isolering verifieras automatiskt (utan grant → nekad).
- [ ] Idempotens-test: retry ger ingen dubblett.
- [ ] Injection-corpus passerar (assistenten lyder inte fientligt innehåll).
- [ ] Eval-svit körs som tröskel för lokal modell-val.
