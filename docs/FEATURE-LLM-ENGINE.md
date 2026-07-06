# LLM-motorn — server-side modell bakom AI-valet (design + byggspec)

Motorn som *konsumerar* `model:`-blocket (CHOOSE-YOUR-LLM.md) som wizarden och
`/app/admin → System → AI-modell` numera skriver. Ger läge 2 (Memaix-egen chatt
+ API-nyckel) och läge 3 (lokal modell) ur `ACCESS-MODES.md`, och den tunna
server-side-loop som `PM-AGENT.md` läge B förutsätter. BYO (läge 1) påverkas
inte — motorn är avstängd när model-blocket saknas.

## Mål
- En användare **utan eget AI-abonnemang** öppnar `/app/chat` och pratar med
  Memaix; gatewayen kör modellen (API-nyckel eller egen endpoint).
- Chatten kan **använda verktygen** (samma 89 MCP-verktyg) med **samma
  behörigheter** som om användaren anslutit via Claude — ingen parallell
  logik, ingen ny rättighetsmodell.
- Leverantören är **pluggbar och utbytbar i drift** via admin-UI:t: Anthropic,
  OpenAI, Google, OpenRouter, Mistral, eller OpenAI-kompatibel/Ollama/vLLM-
  endpoint på lokalt nät eller egen molninstans.

## Icke-mål (v1)
- Ingen röst, ingen mobilapp — chatten är en sida i befintliga `/app`-skalet.
- Ingen multi-agent/planering — en tur = en begränsad agentloop.
- Inga inbäddningar här (semantisk sökning har egen spec och egen modell).
- Byter inte transport för BYO-läget — MCP-connectorn är orörd.

## Arkitektur — tre lager + en konsument

```
gateway/src/memaix_gateway/llm/
  client.py      # Lager 1: provider-adaptrar → ett gemensamt anrop
  toolbridge.py  # Lager 2: befintliga MCP-verktyg → function-calling-scheman
  agent.py       # Lager 3: den begränsade agentloopen (turn-motorn)
web/api/chat.py  # Konsument 1: /app/api/chat (SSE-streaming)
web/pages/chat.html + static/chat.js   # Chatt-UI i app-skalet
```

### Lager 1 — `client.py` (provider-adaptrar)
Ett interface: `complete(messages, tools=None, stream=False) → text | tool_calls`.
- **Adapter `anthropic`** — Messages API (httpx, redan ett beroende; inga
  leverantörs-SDK:er = liten attackyta, jfr AGENTS.md).
- **Adapter `openai-compatible`** — täcker openai, openrouter, mistral,
  ollama, vllm och egen endpoint: samma chat-completions-format, bara olika
  bas-URL. En adapter, fem leverantörsval.
- **Adapter `google`** — Gemini generateContent.
- Config läses per anrop via `config.load()["memaix"]["model"]` (ofärskt
  cache-problem finns inte — admin-ändringen slår igenom direkt); nyckeln via
  `config.secret(api_key_ref)` — aldrig i loggar, aldrig i felmeddelanden.

### Lager 2 — `toolbridge.py` (verktygsbryggan)
- Introspekterar FastMCP-registret → JSON-scheman för function calling.
  **Inget verktyg dubbelregistreras**; bryggan är en vy, inte en kopia.
- Kör verktyg **som den inloggade användaren**: en process-intern contextvar
  (`_agent_user`) som `server._user()` konsulterar FÖRE OAuth-fallet. Sätts
  enbart av agentloopen utifrån den verifierade webbsessionen (samma cookie
  som `/app`), aldrig från requestdata. → ACL, rate-limits, outbox och audit
  träffas exakt som idag.
- Verktygsurval per tur: rollfiltrerat (readers får inte se skriv-verktyg i
  schemat — inte bara nekas vid anrop). Klassningen presenteras i tre nivåer
  (format från agent-skills-utvärderingen, SELF-IMPROVING-SYSTEM.md):
  **Never** = utanför schemat för rollen · **Ask** = via outbox (mänsklig
  bekräftelse) · **Always** = fritt för rollen. Samma regler som SAFETY.md —
  bara läsbart.

### Lager 3 — `agent.py` (turn-motorn)
- Begränsad loop: max `N` verktygsrundor per tur (default 8), max-tokens per
  tur och per dygn/användare (config under `model:`, doctor varnar utan tak).
- Streamar text-deltan via SSE; verktygsanrop visas som statusrader i UI:t
  ("kör calendar_list…") — transparens är en produktprincip.
- Varje verktygsanrop auditloggas med `source=chat` (skiljer chatten från
  MCP-anrop i `/app/admin → Audit`).

### Konsument 1 — chatten
- `POST /app/api/chat` (SSE-svar), historik i SQLite per användare (samma
  mönster som outbox/notify-lagren; vaulten är för kunskap, inte transkript).
- `chat.html` i app-skalet; syns i menyn **bara när model-blocket finns** —
  BYO-användare ser ingen halvfunktion.
- Admin-UI:t får en **"Testa anslutning"**-knapp (minimalt anrop via lager 1,
  svarar modellnamn + latens) — samma sak som doctor-kontrollen kör.

### Konsument 2 (senare, egen fas) — PM-läge B
Schemalagda PM-uppgifter återanvänder lager 1–3 headless (`PM-AGENT.md`).
Specas inte vidare här; motorn byggs så att den inte behöver byggas om.

## Säkerhet (obligatorisk, byggs i Fas 1–2 — inte efteråt)
1. **Prompt injection:** verktygsresultat (mejl, kalendrar, filer) är
   opålitlig indata. Systemprompten markerar verktygsblock som data; skriv-
   åtgärder går via outbox precis som idag (SAFETY.md ändras inte).
2. **Egress:** utgående LLM-trafik får bara gå till den konfigurerade
   leverantörens värd. Endpoint-URL:er valideras (http(s), ingen redirect-
   följning till andra värdar, spärr mot länk-lokala/metadata-adresser —
   samma SSRF-princip som säkerhetsgenomgången införde).
3. **Hemligheter:** nyckeln läses vid anrop, hålls inte i minnet mellan turer,
   syns aldrig i fel/loggar/audit. 4xx från leverantören saneras innan de når
   klienten.
4. **Kostnadstak:** per-tur och per-dygn (fail closed med vänligt fel).
   Räknare i samma SQLite-lager som historiken; syns i admin → System.
5. **Rate limit per användare** på `/app/api/chat` (befintligt `_rl`-mönster).

## Faser (en PR per fas, CI-grön innan nästa)

**Fas 1 — klient + "testa anslutning"** *(ingen ny yta för slutanvändare)*
`llm/client.py` med de tre adaptrarna · `POST /app/api/admin/llm/test`
(admin+MFA) · knapp i admin-UI:t · doctor-kontroll "modell svarar".
✅ Klar när: testknappen ger modellnamn+latens mot riktig Anthropic-nyckel,
mot Ollama på LAN och mot OpenRouter; nyckeln förekommer inte i någon logg.

**Fas 2 — verktygsbrygga + agentloop (headless) — ✅ byggd**
`llm/toolbridge.py`: vy över FastMCP-registret (inget dubbelregistreras);
rollfilter ur förmåge-katalogens needs_role (en sanning för synlighet OCH
upptäckbarhet); identitet via `llm/identity.py`:s AGENT_USER-contextvar
(egen modul — llm-lagret är MCP-oberoende, ett kontrakt en definition),
satt/återställd i finally runt varje anrop; anrop går genom SAMMA
funktionsobjekt som MCP → ACL/outbox/rate-limits/audit ärvs, audit-taggen
`chat:<tool>` loggar arg-nycklar aldrig värden. `llm/agent.py`: begränsad
loop (max_rounds 8), tak per tur och per dygn (SQLite — överlever omstart,
fail closed), systemprompt med otrodd-data-regeln + minnestrappan,
transportneutral on_event (SSE kopplas i Fas 3). Klienten: neutralt
meddelandeformat, verktygsöversättning för anthropic + openai-kompatibel;
google text-utan-verktyg i v1 med admin-varning (specens öppna fråga föll
ut som planerat).
✅ Verifierad med tester 2026-07-06: scriptade kalendersamtalet kör
calendar_list som rätt användare; reader ser inte skriv-verktyg och nekas
även vid gissat namn; identiteten återställs även vid verktygskrasch;
dygnstaket överlever processomstart. Outbox-garantin är arkitektonisk:
samma funktionsobjekt som MCP — ingen parallell väg finns att testa.

**Fas 3 — chatt-UI**
`/app/chat` med SSE-streaming, historik, verktygs-statusrader ·
menyn visar chatten bara med aktivt model-block · i18n sv/en.
✅ Klar när: Playwright-e2e skickar en fråga mot en mockad leverantör och
ser streamat svar + verktygsstatus.

**Fas 4 — drift & finish**
Kostnadsräknare i admin → System · per-dygns-tak · dokumentuppdatering
(ACCESS-MODES: läge 2/3 "✅ byggd", CHOOSE-YOUR-LLM, INDEX).

## Öppna frågor (icke-blockerande, defaults valda)
- Historikens livslängd: default 90 dagar, städjobb i notify-schemaläggarens
  loop. Ändras i config.
- Gemini function-calling avviker mest från de andra två — om adaptern drar
  ut på tiden får `google` i v1 falla tillbaka på text-utan-verktyg med tydlig
  admin-varning, hellre än att försena Fas 2/3.
