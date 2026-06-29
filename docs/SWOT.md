# SWOT — Memaix

Ärlig nulägesanalys, grundad i hela planen + två externa granskningar + självkritiken (OPEN-GAPS).
Inte en pitch — en strategisk karta.

## Styrkor (internt +)
- **AI-agnostiskt via öppen MCP-standard** — ingen inlåsning; byt AI fritt. Få gör detta.
- **Self-host / dataägande av *system-of-record*** — minne/kunskap/filer ligger hos kunden. (Full
  zero-egress kräver **lokal modell**; med moln-AI = ägande + kontroll, inte noll överföring — se ärlig
  invändning i syntesen.)
- **Tvålagersmodellen** — delat minne (kunskap) + projektledaragent (handling). Tydligt, differentierat.
- **Deterministisk motor** (matematik i kod, LLM i kanterna) — pålitligt; gör att även små/lokala modeller fungerar.
- **Single-tenant-isolering** — ren dataseparation, enterprise-vänligt.
- **Genomarbetad plan** — 2 externa granskningar + självkritik; hotmodell, import, tester redan adresserade i planeringsstadiet.
- **Låg marginalkostnad att drifta** — containeriserat, SQLite, billig infra.

## Svagheter (internt −)
- **Hög setup-komplexitet** trots wizard/auto-install — self-host är en reell tröskel.
- **Supportkostnad skalar med kunder** (single-tenant) — marginalpress, driftstungt.
- **Litet team, förprodukt** — exekveringskapacitet och bus factor; ingen användarvalidering än.
- **Brett scope** — gateway, Hydra, Nextcloud, PM-motor, plugins, lokala modeller… mycket för få personer → risk för halvbyggt.
- **Ingen kod-moat** (AGPL, publik) — konkurrent kan drifta samma kod.
- **Kvalitetstak på lokala modeller** för agentiskt verktygsanrop.
- **Beroende av omoget MCP-/OAuth-ekosystem** (klient-egenheter, brytande ändringar).

## Möjligheter (externt +)
- **Stigande efterfrågan på integritets-först AI** — EU-reglering, Schrems II, AI Act driver det.
- **Nischer som *inte får* använda Copilot** — juridik/finans/vård/myndighet. OBS: löses bara med
  **lokal modell**; med moln-AI kvarstår samma egress-problem (se syntesen).
- **MCP-standardiseringen skapar ett ekosystem** — rid på vågen (plugins, connectors).
- **"Bring your own AI" resonerar** när modell-landskapet fragmenteras (Claude/GPT/Mistral/öppna).
- **PM/PMO + kunskapsbas som betalmoduler** — tydlig uppförsäljning, hög marginal.
- **White-label / tjänsteaffär** för byråer och konsulter.
- **Öppen källkod som trovärdighets-/marknadskanal** — granskbarhet säljer mot integritetsköpare.
- **Lokala modeller mognar snabbt** — sovereignty-storyn stärks över tid.

## Hot (externt −)
- **Stora aktörer** (Microsoft Copilot, Google, OpenAI, Nextcloud Assistant) — bekvämlighet + distribution slår self-host för de flesta.
- **Bekvämlighetsbias** — majoriteten av SMB väljer ett-klicks-molnet.
- **Säkerhetsincident = ryktesdöd** — en AI-på-mejl-produkt med ett intrång (prompt injection!) är existentiellt. Därför är hotmodellen kritisk.
- **AI-leverantörers villkor skiftar** — pris, no-train-garantier, planer för skrivåtkomst.
- **MCP-/OAuth-ekosystemet ändras** under fötterna (jfr Cloudflare/iOS-buggen).
- **Konkurrent driftar er AGPL-kod** och överbjuder på marknadsföring.
- **Juridisk/ansvarsexponering** när AI agerar på data; reglering i rörelse (AI Act).

## Vad SWOT:en säger oss (syntes)
- **Styrkor × Möjligheter (offensiv):** en enda kil — *integritets-först, AI-agnostiskt, för dem som
  inte kan/vill köra Copilot*. Gå **smalt** mot en sådan nisch först; bredda sen.
- **Svagheter × Hot (försvar):** de existentiella riskerna är **(1) en säkerhetsincident** (→ hotmodellen
  är inte valfri) och **(2) ett litet team som sprider sig för tunt** (→ sekvensera stenhårt,
  validera med design-partners *före* full byggnation).
- **Ingen kod-moat → moaten är tjänst, expertis, varumärke och moduler** (inte koden). Sälj utfall, inte kod.
- **Bekvämlighetsbias är den tysta dödaren** → setup-förenklingen (trial/auto-install) är inte UX-polish,
  den är *överlevnad*.

## Ärlig invändning: "privacy-flykt från Copilot" håller inte rakt av
Om man inte får köra Copilot för att *data inte får gå till tredjeparts moln*, löser **inte** Memaix
det med en **moln-AI** (Claude/ChatGPT/Mistral) — då går det lästa innehållet till *den* leverantören
istället, ofta samma USA-moln. Med *fler* anslutbara AI:er har man dessutom potentiellt **mindre**
kontroll om det inte styrs. **Full sovereignty (inget lämnar) kräver lokal modell (läge 3).**

Därför, ärligt två separata löften:
- **"Data får inte lämna huset"-nischen** → betjänas av Memaix **bara med lokal modell**. Den äkta
  Schrems-II-säkra konfigurationen — smal men reell.
- **Bredare marknad (moln-AI)** → vinkeln är **ägande + kontroll + ingen inlåsning**, *inte* noll
  överföring. Du äger system-of-record (minne/kunskap/filer), **styr vad som skickas** (retrieval,
  minimering, RBAC, draft-only) — mer granulärt än att ösa allt i Copilot — och är inte gift med en
  leverantör. Starkare än Copilot på *kontroll*, men inte "inget lämnar".

## Den enda meningen (korrigerad)
Memaix vinner på **två skilda löften, inte ett**: för zero-egress-nischen — *"din assistent, helt lokal
AI, inget lämnar huset"*; för alla andra — *"äg din kunskap, styr vad som delas, byt AI fritt"*. Båda
kräver låg setup-tröskel och löst injection-försvar. **Blanda inte ihop dem** — det var precis
misstaget i den tidigare Copilot-vinkeln.
