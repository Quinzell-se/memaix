# SWOT — Memaix

Ärlig nulägesanalys, grundad i hela planen + två externa granskningar + självkritiken (OPEN-GAPS).
Inte en pitch — en strategisk karta.

## Styrkor (internt +)
- **AI-agnostiskt via öppen MCP-standard** — ingen inlåsning; byt AI fritt. Få gör detta.
- **Self-host / dataägande** — stark integritets-/compliance-story (EU, Schrems II, AI Act).
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
- **Nischer som *inte får* använda Copilot** — juridik/finans/vård/myndighet, underbetjänade.
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

## Den enda meningen
Memaix vinner om det blir **det självklara valet för dem som av juridiska/integritetsskäl inte kan
lägga sin data i Copilot** — levererat med så låg setup-tröskel att bekvämlighetsbias inte hinner döda
det, och med säkerheten (injection!) löst så att en incident aldrig får inträffa. Allt annat är sekundärt.
