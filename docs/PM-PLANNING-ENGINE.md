# PM-modulen — planeringsmotorn (resurser, allokering, konsekvens, rapport)

Hur PM-agenten **på riktigt** ska kunna planera resurser, planera och allokera arbetsuppgifter,
följa upp, analysera konsekvenser och rapportera. Fördjupar `ADDON-PM-BUILD.md`; följer
determinismgränsen i `PM-AGENT.md`.

## Kärninsikt
De svåra förmågorna är **deterministiska beräkningsproblem**, inte språkproblem. Bygg en riktig
**planeringsmotor i kod**. LLM:en är gränssnittet: fångar avsikt, förklarar, flaggar, rapporterar —
**räknar aldrig**.

## Datamodell (i SQLite — aktivt tillstånd)
- **Resurser:** person, kapacitet/period, tillgänglighet (kalender, semester, deltid), kompetenser,
  kostnad/timme.
- **Uppgifter:** estimat, beroenden (`depends_on`), krävd kompetens, prioritet, milstolpe, tilldelning.
- **Baseline:** den godkända planen (referens för variansanalys).
- **Actuals:** framsteg/%, nedlagd tid, status (för uppföljning).
- **Scenarier:** isolerade kopior för what-if.

## Förmågorna → så löses de
| Förmåga | Teknik (deterministisk) | LLM:ens roll |
|---|---|---|
| **Resursplanering** | kapacitetsmodell över tid (kalendrar, kompetens) | fånga tillgänglighet/kompetens i naturligt språk |
| **Uppgiftsplanering** | WBS + beroendegraf + estimat | dekomponera mål → uppgifter, föreslå estimat |
| **Allokering** | resursbegränsad schemaläggning (RCPSP): heuristik eller CP-SAT-solver | förklara avvägningar, föreslå prioritet |
| **Uppföljning** | actuals vs baseline → varians, framdrift, slippage | sammanfatta läget, flagga avvikelser |
| **Konsekvensanalys (what-if)** | scenario: ändra input → räkna om kritisk linje + resurskonflikter + milstolpsdatum → diffa mot baseline | berätta konsekvensen, rekommendera åtgärd |
| **Rapportering** | rollups: utnyttjandegrad, burndown, milstolpstatus, RAID | skriva narrativet, anpassa nivå (team/ledning) |

## Motorvalet (tekniskt bäst)
- **Schemaläggning / kritisk linje:** grafmatematik (topologisk sortering, forward/backward pass) —
  enkelt och exakt.
- **Resursallokering / leveling:** **Google OR-Tools (CP-SAT)** är guldstandard för resursbegränsad
  schemaläggning (öppen källkod, gratis). **v1:** enklare prioritetsbaserad list-scheduling-heuristik;
  uppgradera till CP-SAT när komplexiteten kräver.
- **What-if:** klona scenariot, applicera ändringen, kör om motorn, **diffa**. Scenarier hålls
  åtskilda från den committade planen.
- **Lagring:** allt i SQLite (aktivt tillstånd); baseline/scenarier som versioner; git async för historik.

## Verktyg (utöka `pm_*`)
`resource_add/list/availability`, `task_estimate/assign`, `allocate` (kör motorn),
`whatif` (simulera scenario), `utilization` (utnyttjandegrad), `variance` (plan vs utfall),
`report` (generera). Alla projekt-scopade, RBAC; planändringar = owner.

## LLM-gränsen (helig)
LLM:en räknar **aldrig** schema, kritisk linje, kapacitet eller datum. Den (a) fångar avsikt och
begränsningar i naturligt språk → strukturerad input, (b) förklarar motorns resultat, (c) flaggar
risker, (d) skriver rapporter. Owner committar planändringar.

## Ärligt om begränsningarna
- **RCPSP är NP-svårt** — för stora projekt ger man heuristik/solver, inte exakt optimum. "Tillräckligt
  bra + förklarbart" slår "optimalt + svart låda".
- **Garbage in, garbage out.** Planen är bara så bra som estimaten och tillgänglighetsdatan. Kräv
  rimliga estimat, flagga osäkerhet, **gissa aldrig datum**.
- **Människan beslutar.** Motorn föreslår, AI:n förklarar, owner godkänner. Sälj inte "AI:n planerar
  dina resurser" — sälj "beräknad, förklarad, mänskligt godkänd plan".

## Faser
1. **Datamodell** (resurser/uppgifter/kalendrar) + **kritisk linje** + utnyttjandegrad-rapport.
2. **Kapacitetsbaserad allokering** (heuristik) + **baseline** + **varians** (uppföljning).
3. **What-if-scenarier** (konsekvensanalys) + Gantt/diff-rapport.
4. **CP-SAT-optimering** för tyngre allokering + resursutjämning.
5. **Rapportpaket** (utnyttjande, burndown, milstolpe, RAID) per publik.

## Acceptanskriterier
- [ ] Resurser modelleras med kapacitet, tillgänglighet och kompetens.
- [ ] Allokering respekterar kapacitet + kompetens + beroenden, deterministiskt.
- [ ] What-if visar konsekvens (kritisk linje / milstolpe / konflikter) diffad mot baseline.
- [ ] Uppföljning visar varians plan vs utfall.
- [ ] All beräkning sker i kod; LLM endast gränssnitt; owner committar planändringar.
