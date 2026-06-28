# Åtkomstlägen — använda Memaix utan egen AI-klient

"Bring your own AI" (MCP-connector) är **ett** sätt att nå Memaix — för team som redan har Claude/
ChatGPT/Mistral. Men `pm_*`- och övriga verktygen + datamodellen utgör i praktiken ett **internt API**
som *vilken frontend som helst* kan använda. Det öppnar flera vägar för dem utan eget AI-abonnemang.

## Den bärande insikten
Verktygslagret (MCP-verktyg) + planeringsmotorn + datamodellen är **drivande-agnostiska**. En frontend
— egen AI-klient, Memaix-egen webbchatt, en bot, eller ett rent GUI — anropar samma verktyg och samma
data. Att lägga till en frontend **forkar ingen logik**.

## Frågan handlar egentligen om: var körs modellen, och vem betalar?

| Läge | LLM körs | Vem betalar modellen | Data lämnar instansen? | Kvalitet | Bäst för |
|---|---|---|---|---|---|
| **1. BYO AI** (MCP-connector) | användarens AI-klient (moln) | användaren (sitt abonnemang) | ja → deras AI-leverantör | hög | team som redan har Claude/ChatGPT/Mistral |
| **2. Memaix-egen chatt + API-nyckel** | server-side via API | kund/operatör (API-tokens) | ja → vald API-leverantör | hög | de **utan** eget AI-abonnemang |
| **3. Lokal öppen modell** | server-side på kundens GPU | kund (hårdvara, inga tokens) | **nej — inget lämnar boxen** | medel | max integritet (Schrems II), reglerat |
| **4. Deterministiskt GUI** (ingen AI) | — ingen LLM | ingen | nej | n/a | de som bara vill ha motorn/kunskapsbasen |
| **5. Chatt-bot** (Slack/Teams/Discord) | server-side via API | kund (tokens) | ja → API + chattplattform | hög | team som lever i Slack/Teams |

## Rimliga vägar att utvärdera (för "utan egen AI")

**2. Memaix-egen webbchatt (server-side modell).** Memaix levererar en egen chatt-frontend; gatewayen
anropar en LLM via en **API-nyckel kunden anger** (Anthropic/OpenAI/Mistral). Användaren öppnar bara
Memaix och chattar — inget eget AI-abonnemang. Bygger på samma server-side-agentloop som PM-läge B
(`PM-AGENT.md`). *Kostnad: API-tokens (kan vara billigare än per-säte vid lätt användning).*

**3. Lokal öppen modell (Ollama/vLLM + Llama/Qwen/Mistral).** Server-side modell på kundens egen
hårdvara → **ingen data lämnar ens till en AI-leverantör.** Det är det starkaste möjliga svaret på
Schrems II/sekretess (jfr `LEGAL.md`). *Pris: GPU/hårdvara, inga tokens. Haken: öppna modeller är
svagare på komplext agent-resonemang och verktygsanrop — testa kvaliteten innan löfte.*

**4. Deterministiskt GUI utan AI.** Stor del av värdet — resursallokering, kritisk linje, what-if,
rapporter, kunskapsbasen — är **deterministiskt** och behöver ingen LLM. Ett vanligt webb-GUI (formulär,
dashboards, Gantt) över samma datamodell ger Memaix som självhostat PM-/kunskapsverktyg där AI:n är
*valfri grädde*. Det är "golvet": nyttigt även med noll AI.

**5. Chatt-bot i Slack/Teams/Discord.** Server-side agent svarar i verktyg teamet redan använder.
Möter dem där de är; operatören betalar API.

## Implikationer
- **"AI-agnostiskt" flyttar sig** från klient till backend: modellen blir pluggbar (API eller lokal),
  men Memaix äger då frontend:en (chatt/GUI) — mer att bygga och underhålla.
- **Bredare marknad:** kravet "måste ha egen Claude/ChatGPT" försvinner → träffar dem som
  affärscaset (`BUSINESS-CASE.md`) annars tappade till bekvämlighet.
- **Säkerhet/juridik:** läge 3 (lokal modell) eliminerar tredjepartsöverföringen helt — ett reellt
  säljargument för reglerade köpare.
- **Kostnad:** API-lägen flyttar kostnaden från per-säte till per-token; lokal modell till hårdvara.

## Rekommendation
- **Primärt alternativ utan egen AI:** läge **2** (Memaix-egen chatt + kundens API-nyckel), med läge
  **3** (lokal modell) som integritets-maximalt val.
- **Alltid-golv:** bygg det **deterministiska GUI:t** (läge 4) över planeringsmotorn — det gör Memaix
  värt något även helt utan AI, och sänker tröskeln rejält.
- Allt delar samma verktyg/data → ingen dubblerad logik, oavsett hur många frontends ni stödjer.

## Att utvärdera innan beslut
- [ ] Kvalitet på lokala modeller för agent-/verktygsanrop (läge 3) — testa, lova inte i förväg.
- [ ] Bygg-/underhållskostnad för egen chatt-UI + agentloop (läge 2).
- [ ] Token-kostnad vid server-side modell vs per-säte-abonnemang — räkna på typisk användning.
- [ ] Hur mycket av PM-värdet som står på egna ben i ett rent GUI (läge 4).
