# Utvärdering — tilläggstjänst: AI-projektledare (agil + vattenfall)

Förslag: en betald tilläggsmodul där en AI-agent är extremt skicklig på **både** agil och
vattenfalls-projektledning, metodikmedveten per projekt.

## Slutsats först
**Bygg den — men som fokuserad MVP, metodikmedveten, ovanpå backloggen.** Det är den starkaste
naturliga uppförsäljningen: den förvandlar "delad backlog" till ett **AI-projektkontor**.
Differentieringen: *dubbel metodik + self-hosted + AI-agnostiskt* — det gör nästan ingen.

## Varför passformen är ovanligt bra
Memaix har redan PM-primitiven:
- **Backloggen** = arbetsenheten (items, kategorier, status-flöde).
- **Poängsättningen** (nytta/komplexitet/risk) = estimering + riskhantering, redan inbyggt.
- **Minnet** = projekthistorik, beslut, RAID-logg.
- **RBAC** = vem får ändra planen (owner) vs se den (reader).

En PM-agent är "strukturerad kunskap + arbetsflöde + beslut över tid" — exakt Memaix kärna.

## Vad agenten gör

**Agilt:**
- Backlog-grooming, story-slicing, sprintplanering, estimering (återanvänder poängaxlarna).
- Standup-sammanfattningar (läser uppdateringar ur minne/backlog), burndown, retro-facilitering.

**Vattenfall:**
- WBS, fas-/Gantt-planering, beroenden, kritisk linje, milstolpar.
- Ändringshantering (backloggens status-flöde + risk = change control board), stage gates.
- RAID-logg (Risks/Assumptions/Issues/Dependencies) i vaulten.

**Hybrid:** välj metodik per projekt (`methodology: agile | waterfall | hybrid`) — många riktiga
organisationer är hybrida. Agenten anpassar ceremonier, artefakter och vokabulär därefter.

## Hur den byggs (teknik)
- En **plugin/skill-pack** ovanpå gatewayen: nya verktyg `sprint_*`, `gantt_*`, `milestone_*`,
  `raid_*`, `report_*`.
- **Artefakter som markdown** i vaulten (sprintplaner, roadmaps, RAID-loggar) → versionerat i git,
  läsbart av människor, valfritt renderat (Mermaid Gantt).
- **Metodikmotor:** `SKILL.md` per metodik som agenten följer; läser projektets `methodology`.
- **Deterministisk schemaläggning:** kritisk linje och beroenden räknas med riktig algoritm — AI:n
  *berättar och resonerar*, men matematiken är kod, inte gissning.
- **Owner-beslut:** planändringar kräver owner-roll (samma RBAC som backlog-status).

## Differentiering mot marknaden
De flesta AI-PM-verktyg klistras ovanpå Jira/Asana (SaaS, din data i deras moln). Memaix
PM-agent kör på **din data, din infra, valfri AI** — och behärskar **båda** metodikerna. Positionera
som *det självhostade AI-projektkontoret*. Alternativ väg: integrera mot Jira/MS Project via MCP
(läs befintliga projekt) snarare än att ersätta — möter företag där de är.

## Risker och hur de hanteras
- **Scope creep.** PM är enormt. MVP = backlog→sprintplanering + en roadmap/Gantt + statusrapport.
  Allt annat efter validering.
- **Kvalitetskrav.** Dålig PM-rådgivning är värre än ingen. Guardrails + mänskligt godkännande för
  planändringar. Deterministisk schemaläggning, inte "vibes".
- **Etablerade konkurrenter (Jira, MS Project).** Konkurrera inte på funktionsbredd — konkurrera
  på *self-hosted + AI-agnostiskt + dubbel metodik*, eller integrera istället för att ersätta.
- **Metodik-förvirring.** Tydlig per-projekt-metodik; agenten blandar inte agilt och vattenfall
  omedvetet.

## Affärsmodell för tillägget
Passar open-core perfekt: kärn-Memaix gratis, **PM-agenten som betald modul** (per-instans-licens
eller säte) eller del av en Pro/Business-tier. Plus tjänsteuppsäljning — du konfigurerar PM-flödet
åt kunden. Sub-brand t.ex. "Memaix PMO".

## Förslag på faser
1. **MVP:** metodik-config + backlog→sprintplanering (agilt) och WBS+milstolpar (vattenfall) +
   statusrapport som fil. Allt i markdown/vault.
2. **Schemaläggning:** beroenden, kritisk linje, Gantt (Mermaid-render).
3. **Ceremonier:** standup/retro (agilt), stage gates/change control (vattenfall), RAID-logg.
4. **Integrationer:** läs Jira/MS Project via MCP; tvåvägs där det är säkert.
5. **Rapporter & dashboards:** burndown, milstolpstatus, risk-heatmap som genererade filer.

## Rekommendation
Ja. Det är den mest logiska första betalmodulen eftersom den bygger direkt på backloggen och
poängsättningen som redan finns. Börja smalt (sprintplan + roadmap + statusrapport), håll
schemaläggningen deterministisk, och sälj på det ingen annan har: **en självhostad,
AI-agnostisk projektledare som behärskar både agilt och vattenfall.**
