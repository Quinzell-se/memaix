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

## Fas A — Väktaren (självövervakning → självreparation) — ✅ byggd
`scripts/watchdog.py` + `ops/memaix-watchdog.{service,timer}` (systemd user-units, var 6:e
timme + vid boot; installationskommandon i .service-filen). Kontroller: gateway/hydra lokalt,
publik URL genom tunneln, **publikt serverad frontend-hash == diskens app.js** (§6b regel 1),
**config skrivbar i containern** (§6b regel 2), klon-drift mot origin (info). Fel i
gateway/hydra/tunnelkedja → `docker compose restart` av felande tjänst, EN gång → omkontroll →
notis bara vid avvikelse. Frontend/skrivbarhet/drift läks aldrig automatiskt — rebuild och
deploy är människans beslut (anti-hype-listan).
Notis v1: `WATCHDOG_WEBHOOK_URL` (+ `WATCHDOG_WEBHOOK_FMT: raw|discord`) i `.env` — samma
semantik som notify-lagrets WebhookChannel; utan URL loggas till journalen. Byte till
notify-lagret när Fas C landar.
✅ **Verifierad i drift 2026-07-06:** avsiktligt stoppad gateway självläkte utan människa
(upptäckt → omstart → omkontroll → "Självläkte"-notis). Driftsättningen fångade även en
väktarbugg: Cloudflare 403:ar Pythons default-User-Agent → falsklarm + onödig tunnelomstart;
fixad med egen UA + regressionstest (PR #16). Lärdom: en ny monitors första larm testar
monitorn, inte systemet.

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
Fröer: verifierings-checklistorna i addyosmani/agent-skills (MIT) — security- och debugging-
skillens "Never"-listor översätts till neka-fall (LLM-output i skal/SQL, otrodd data som
instruktion, hemligheter i utgående innehåll) där de mappar mot Python/MCP-världen.
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

## Lånade format (utvärdering av addyosmani/agent-skills, 2026-07-06)
Beslut efter granskning av repot (24 skills, MIT, 70k stjärnor):
- **Stjäl mekanismerna, inte paketet.** Pluginen installeras INTE — överlappar befintliga
  verktyg (feature-dev, pr-review-toolkit, code-review), webbstack-slagsida (npm/innerHTML),
  och 24 skill-beskrivningar sväller varje sessionskontext. Generisk lore < egna incidenter.
- **Anti-rationaliseringstabeller** (deras bästa mekanism) — antagen i AGENTS.md §6b med rader
  ur våra egna incidenter. Modellen rationaliserar genvägar; systemet ska bära motargumentet.
- **Always/Ask First/Never-nivåerna** (deras security-skill) — antaget som presentationsformat
  för verktygsklassning i LLM-motorns brygga (FEATURE-LLM-ENGINE Fas 2): rollfiltrerade verktyg
  = Never-nivån, outbox = Ask-nivån. Sak samma som SAFETY.md redan kräver — men läsbart i tabell.
- **Verifierings-checklistor** → fröer till Fas D (se ovan).

## Ordning & beroenden
A är fristående (bygg först — billigast, störst driftvärde). B är fristående. C kräver B
(statusen) och LLM-motorns Fas 2 för LLM-varianten. D byggs ihop med motorns Fas 2–3. E sist.
