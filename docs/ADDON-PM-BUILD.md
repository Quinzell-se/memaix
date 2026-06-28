# Bygg-spec — PM-modulen (MVP)

Implementationsspec för "Memaix PMO": en metodikmedveten AI-projektledare (agil + vattenfall) som
betald tilläggsmodul. Bygger ovanpå backloggen och poängsättningen som redan finns i kärnan.
Bakgrund och affär: se `ADDON-PROJECT-MANAGEMENT.md`.

## Princip
AI:n **resonerar och berättar**; **matematiken är kod** (schemaläggning, kritisk linje, kapacitet).
Planändringar kräver `owner`. Allt är markdown i projektets vault → versionerat i git.

## Metodik per projekt
Sätts i projektets `playbook.md` frontmatter (eller via `pm_set_methodology`):
```yaml
methodology: agile        # agile | waterfall | hybrid
sprint_length_days: 14    # agilt
capacity: { bob: 8, carol: 5 }   # poäng/dagar per person & sprint
```
Agenten läser detta och tillämpar rätt ceremonier, artefakter och vokabulär. `SKILL.md` per
metodik (`pm/skills/agile.md`, `pm/skills/waterfall.md`).

## Backlog-fält som PM-modulen lägger till (valfria)
Utökar item-frontmatter — påverkar inte kärnans backlog:
```yaml
estimate:                 # story points (agilt) eller dagar (vattenfall)
sprint:                   # t.ex. SPRINT-03
milestone:                # t.ex. M2
depends_on: []            # lista av item-id → schemaläggning
```

## Artefakter (markdown i `<projekt>/pm/`)
```
pm/
  roadmap.md              # milstolpar + Gantt (Mermaid)
  raid.md                 # Risks / Assumptions / Issues / Dependencies
  sprints/SPRINT-03.md    # mål, valda items, kapacitet, resultat
  reports/STATUS-YYYY-MM-DD.md
```

## Verktyg (pm_*)
| Verktyg | Funktion | Roll |
|---|---|---|
| `pm_set_methodology` | Sätt agile/waterfall/hybrid + parametrar | owner |
| `pm_plan_sprint` | Agilt: välj backlog-items till sprint efter kapacitet | owner (collaborator föreslår) |
| `pm_sprint_status` | Burndown/sammanfattning för en sprint | reader |
| `pm_wbs` | Vattenfall: bygg/läs WBS ur backloggen | reader |
| `pm_milestone_add/list/update` | Milstolpar med datum | owner / reader |
| `pm_schedule` | Deterministisk: beroenden, earliest start/finish, kritisk linje | reader |
| `pm_raid_add/list` | RAID-logg | collaborator / reader |
| `pm_status_report` | Generera statusrapport som fil | reader |

## Schemaläggning (deterministisk, fas 3)
- Topologisk sortering av `depends_on` (upptäck cykler → fel).
- Forward pass med `estimate` → earliest start/finish per item.
- **Kritisk linje** = längsta vägen. Markera items på den.
- Rendera Gantt som Mermaid i `roadmap.md`. AI:n skriver narrativet runt siffrorna.

## Faser
1. **MVP-kärna:** metodik-config + backlog-fält + `pm_status_report` (read-only syntes ur backlog).
2. **Agilt:** `pm_plan_sprint` + `pm_sprint_status` (kapacitetsbaserat urval, burndown).
3. **Vattenfall:** `pm_wbs` + milstolpar + `pm_schedule` (kritisk linje) + Mermaid-Gantt.
4. **Ceremonier & RAID:** standup-/retro-sammanfattningar (agilt), stage gates/change control
   (vattenfall, återanvänder backloggens status-flöde), RAID-logg.
5. **Integrationer:** läs Jira/MS Project via MCP; tvåvägs där det är säkert.

## Guardrails
- Planändringar (`set_methodology`, `plan_sprint`-commit, milstolpsändring) kräver `owner`.
- AI:n får föreslå estimat/prioritet — människan committar.
- Schemaläggning får aldrig vara "ungefär"; saknas estimat → flagga, gissa inte datum.
- Hybrid-projekt: blanda inte metodik omedvetet — agenten deklarerar vilket spår den följer.

## Acceptanskriterier (MVP)
- [ ] Ett projekt kan sättas till agile/waterfall/hybrid och agenten anpassar sig.
- [ ] `pm_status_report` genererar en korrekt rapportfil ur aktuell backlog + minne.
- [ ] Agilt: en sprint planeras efter kapacitet och dess status kan följas.
- [ ] Vattenfall: WBS + milstolpar + en kritisk linje räknas deterministiskt och renderas som Gantt.
- [ ] Alla artefakter committas i projektets vault; planändringar kräver owner.
