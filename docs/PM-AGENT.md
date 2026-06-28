# PM-agenten — arkitektur & best practice

Hur man bygger den specialiserade projektledaragenten *rätt* på Memaix. Kompletterar verktygs-
specen (`ADDON-PM-BUILD.md` / `MCP-API-PM.md`) och affären (`ADDON-PROJECT-MANAGEMENT.md`).

## Princip: specialisering i lager, inte en stor prompt
Specialiseringen bor i fyra lager — inte i en gigantisk systemprompt:
1. **Identitet/instruktioner** — `SKILL.md` + playbook: metodik, vokabulär, kvalitetsgrindar.
2. **Verktyg (deterministiska `pm_*`)** — förmågorna; *matematiken i kod*.
3. **Kontext/minne** — projektstatus (backlog/RAID/historik) via **retrieval**, inte dump.
4. **Guardrails** — owner-godkännande, budgetar, loop-skydd (SAFETY.md).

## Två körlägen — best practice = hybrid
**A. Interaktiv (tunn, AI-agnostisk) — default.** Användarens egen AI (Claude/Mistral) **är** agenten:
den laddar PM-skillen och anropar `pm_*`-verktygen via Memaix. Ingen dedikerad tjänst behövs.
Stbobr i Memaix identitet (AI-agnostiskt, self-hosted).

**B. Autonom/schemalagd (tunn server-side loop).** En liten agent-loop på qronkclawd (Claude Agent
SDK eller eget tunt loop) kör **schemalagda** PM-uppgifter — nattlig statusrapport, deadline-vakt,
sprint-rollover — utan att en människa öppnar en chat. Anropar ett LLM-API + **samma** MCP-verktyg.

Båda delar samma verktyg och samma projektstatus → **ingen dubblerad logik**.

## Best-practice-principer (2026)
- **Smal, djup, single-responsibility.** PM-agenten gör PM, inte allt. Specialiserat slår generalist
  (multi-agent-uppställningar med planerare + sub-agenter slår single-agent rejält på benchmarks).
- **Deterministisk kärna, LLM i kanterna.** Schemaläggning, kritisk linje, kapacitet och rollups i
  **kod**; LLM för dekomposition, narrativ, triage och omdöme. Låt aldrig LLM:en "räkna".
- **Verktyg framför prompt (tool-use-first).** Ge den `pm_schedule` — be den inte räkna kritisk linje
  i huvudet. (Claude Agent SDK:s filosofi: en agent är en modell utrustad med verktyg.)
- **Strukturerad I/O.** Verktyg tar och returnerar **typad data (scheman)**, inte fritext → mindre
  hallucination, mer förutsägbart.
- **Stateless agent, stateful system.** Agenten håller inget långtidstillstånd; allt ligger i Memaix
  (backlog/RAID/historik). Vilken agent-instans som helst kan ta vid. (Speglar granskarnas
  stateless-poäng.)
- **Retrieval, inte dump.** Hämta relevant projektkontext via sök/pagination — aldrig hela historiken
  (SAFETY.md).
- **Människa godkänner planändringar.** Owner-grind (RBAC) för sprintcommit, milstolpar, status.
- **Metodikmedveten.** Läser projektets `methodology` (agile/waterfall/hybrid) och tillämpar rätt
  ceremonier — blandar inte omedvetet.
- **Sub-agenter vid behov.** Komplext (t.ex. "planera kvartalet") kan dekomponeras till sub-agenter
  med **isolerad kontext**, koordinerade av en planerare. Börja med **en** agent; inför sub-agenter
  när uppgiften kräver parallellism eller kontextisolering — inte innan.
- **Evaluerbar.** Definiera en kvalitetschecklista som agenten självkontrollerar mot före leverans,
  plus en liten **eval-svit** (testfall: "given denna backlog → producerar den rätt sprintplan?").
- **Bounded autonomy.** Budgetar, rate limits, loop-detektion; schemalagda körningar har hårt scope.
- **Observability/audit.** Logga vad agenten beslutade och gjorde (OBSERVABILITY.md / audit).

## Hur specialiseringen konkret byggs
- **Skill-pack (plugin-struktur):** `SKILL.md` (metodik-arbetsflöde + kvalitetsgrindar),
  `references/` (mallar: sprintplan, roadmap, RAID), `commands/` (slash: `/pm:plan-sprint`,
  `/pm:status`), och en skill per metodik (`agile.md` / `waterfall.md`).
- **Verktyg:** `pm_*` (redan specat).
- **Autonom loop:** Claude Agent SDK (eller eget tunt loop) triggat av **cron** på qronkclawd för
  schemalagda jobb.

## Rekommendation
Börja med **läge A** (tunn, AI-agnostisk: skill + verktyg) — det ger ~80 % av värdet och behåller
Memaix identitet. Lägg **läge B** (autonom loop) när schemalagda PM-uppgifter behövs. Håll
**determinismgränsen helig** (matematik i kod, LLM för omdöme). **En agent först; sub-agenter när
komplexiteten kräver det.**

## Acceptanskriterier
- [ ] PM-agenten fungerar interaktivt via valfri AI (skill + `pm_*`), utan dedikerad tjänst.
- [ ] Schemalagda PM-uppgifter körs av en tunn server-side loop mot samma verktyg.
- [ ] All beräkning (schema/kritisk linje/kapacitet) sker i kod, inte i LLM.
- [ ] Agenten är stateless; all status i Memaix; planändringar kräver owner.
- [ ] En eval-svit verifierar agentens output mot kända testfall.
