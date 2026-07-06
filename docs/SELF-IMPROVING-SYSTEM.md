# Självförbättrande Memaix — loopar, kontroller & lärande (design + inriktning)

Tes (lånad, prövad, antagen): **självförbättring är en egenskap hos systemet, inte hos modellen.**
Modellen lär sig ingenting mellan sessioner — det som ackumulerar är disciplinen runt den:
minne som destilleras, oberoende verifiering, schemalagda kontroller. Det är också säljbart:
Memaix blir bättre av att användas, oavsett vilken AI kunden kopplar in (AI-agnostiskt, som allt).

## Utgångsläge — organen finns, looparna saknas
Memaix har redan delarna ett självförbättrande system behöver:

| Organ | Finns som | Saknar |
|---|---|---|
| Minne | git-versionerade vaults + SQLite | skillnad hypotes/verifierat; destillering |
| Observation | auditlogg (basal i kärnan), timeline | ingen läser den systematiskt |
| Självdiagnos | `make doctor` | körs bara manuellt; reparerar inget |
| Mänsklig verifierare | outbox (bekräfta utgående), MFA | — (behåll exakt så) |
| Rutinmotor | brief-schemaläggaren (asyncio-loop i gatewayn) | bara brief som konsument |
| Regelverk | automationsregler (stående instruktioner) | ingen återkoppling om de följs |

Inriktningen: **koppla ihop organen till loopar** — inte bygga nya organ.

## Fas A — Väktaren (självövervakning → självreparation)
En systemd-timer på värden (var 6:e timme + vid boot): kör doctor; **röd → \
`docker compose restart` av felande tjänst → doctor igen; fortfarande röd → notis** via
notify-lagret (samma kanal som briefen). Kontrollerna utökas med arbetsflödesregeln
(AGENTS.md §6b): publik URL serverar färsk frontend (hash-jämförelse mot disk), config-mounten
är skrivbar, klonen driver inte mot origin.
✅ Klar när: en avsiktligt stoppad gateway självläker utan människa, och en avsiktligt
cachetrasig frontend ger notis inom 6 h.

## Fas B — Minnestrappan (hypotes → verifierat)
Artikelns bästa idé, och den passar vaulten som handen i handsken: minnesnoteringar får
frontmatter-status **`hypotes` | `verifierad`** (default hypotes). `memory_write` tar emot
status; systemprompten instruerar modellen att (1) märka osäkra påståenden som hypoteser,
(2) befordra först efter bekräftelse i källa/verktyg, (3) vid konsultation väga verifierat
över hypotes. Ingen ny lagring — bara disciplin i den som finns.
✅ Klar när: whoami-/onboarding-prompten bär reglerna och ett test visar att en hypotes-
notering inte presenteras som faktum i brief/sök.

## Fas C — Destillatrutinen (auditlogg → lärdomar)
Veckorutin i brief-schemaläggarens loop, **första headless-konsumenten av LLM-motorn**
(FEATURE-LLM-ENGINE, kräver Fas 2): läs veckans auditlogg + timeline (fel, nekade anrop,
ångrade åtgärder, outbox-avslag) → destillera till en vault-notering "lärdomar/vecka-NN"
(status: hypotes — trappan gäller destillatet också). Utan model-block: rutinen skriver en
deterministisk sammanställning (räknare, toppfel) — värdefull även utan LLM.
✅ Klar när: två veckor i drift gett två destillat och minst en regel befordrats till verifierad.

## Fas D — Eval-sviten (regression för motorn)
Kurerade testsamtal (`gateway/tests_eval/conversations.jsonl`): fråga + förväntade
verktygsanrop + förbjudna åtgärder ("reader ber om mejlutskick → neka"). Körs i CI mot mockad
leverantör (deterministiskt); väktaren kör den veckovis mot riktig konfig och notifierar vid
regression. Byggs ihop med FEATURE-LLM-ENGINE Fas 2–3 — acceptanskriterierna där ÄR de första
eval-fallen; spara dem som svit i stället för att slänga dem.
✅ Klar när: en avsiktligt försämrad systemprompt fångas av sviten före merge.

## Fas E (senare) — Granskarseparation i agentloopen
Billig graderingsmodell som andra ögon på utgående åtgärder mot stående regler, FÖRE outbox.
Djupare försvar, inte ersättning: **människan i outboxen förblir sista ordet.** Byggs först
när chatten (LLM-motorn Fas 3) har verklig trafik att granska.

## Vad vi INTE gör (anti-hype, bindande)
- **Ingen självmodifierande systemprompt.** Destillat är data modellen läser — aldrig
  instruktioner som skriver om instruktioner (THREAT-MODEL: läst innehåll är otrodd data).
- **Ingen auto-merge, ingen auto-deploy.** Väktaren startar om tjänster — den skriver inte kod.
- **Ingen självbefordran.** En hypotes blir verifierad genom källbekräftelse eller människa —
  aldrig genom att modellen tycker att den låter rimlig.
- **Outbox/MFA försvagas aldrig** i självförbättringens namn (AGENTS.md §2 gäller över detta).

## Ordning & beroenden
A är fristående (bygg först — billigast, störst driftvärde). B är fristående. C kräver B
(statusen) och LLM-motorns Fas 2 för LLM-varianten. D byggs ihop med motorns Fas 2–3. E sist.
