# Memaix MCP-API — PM-modulen (tillägg)

Verktygsreferens för PM-modulen ("Memaix PMO"). Följer samma konventioner som kärn-API:t
(`MCP-API.md`): `project` obligatoriskt, RBAC före varje anrop, ISO 8601-tider, artefakter som
git-committad markdown i `<projekt>/pm/`. Bakgrund: `ADDON-PROJECT-MANAGEMENT.md`,
bygg-ordning: `ADDON-PM-BUILD.md`.

## Metodik

| Verktyg | Parametrar | Returnerar | Roll |
|---|---|---|---|
| `pm_set_methodology` | `project, methodology, sprint_length_days?, capacity?` | `{project, methodology, sprint_length_days, capacity}` | **owner** |

- `methodology`: `agile` \| `waterfall` \| `hybrid`.
- `capacity`: objekt `{användare: poäng_eller_dagar}` per sprint/period.
- Styr vilka övriga verktyg som är meningsfulla och vilken vokabulär agenten använder.

## Agilt — sprintar

| Verktyg | Parametrar | Returnerar | Roll |
|---|---|---|---|
| `pm_plan_sprint` | `project, name, start, end, item_ids[], goal?` | `{sprint, items, committed_points, over_capacity:bool}` | **owner** (collaborator föreslår) |
| `pm_sprint_status` | `project, sprint` | `{sprint, total, done, remaining, burndown:[{date, remaining}], at_risk:[id]}` | reader |

- `item_ids` refererar backlog-items. `committed_points` summeras från items `estimate`.
- `over_capacity: true` om summan överstiger `capacity` — agenten flaggar, beslutar inte.

## Vattenfall — WBS, milstolpar, schema

| Verktyg | Parametrar | Returnerar | Roll |
|---|---|---|---|
| `pm_wbs` | `project` | `{tree:[{id, title, estimate, children:[...]}]}` | reader |
| `pm_milestone_add` | `project, name, date, description?` | `{id}` | **owner** |
| `pm_milestone_list` | `project` | `[{id, name, date, status, items:[id]}]` | reader |
| `pm_milestone_update` | `project, id, {name?, date?, status?}` | `{id}` | **owner** |
| `pm_schedule` | `project` | `{tasks:[{id, earliest_start, earliest_finish, critical:bool}], critical_path:[id], finish_date, gantt_mermaid}` | reader |

- `pm_wbs` byggs ur backloggens items (och deras `milestone`-fält).
- `pm_schedule` är **deterministisk**: topologisk sortering av `depends_on`, forward pass med
  `estimate`, kritisk linje = längsta vägen. `gantt_mermaid` är renderbar Mermaid-kod.
- `validation_error` om estimat saknas eller `depends_on` innehåller en cykel — inga gissade datum.

## RAID-logg

| Verktyg | Parametrar | Returnerar | Roll |
|---|---|---|---|
| `pm_raid_add` | `project, type, text, owner?, severity?` | `{id}` | collaborator |
| `pm_raid_list` | `project, type?` | `[{id, type, text, severity, status, owner}]` | reader |

- `type`: `risk` \| `assumption` \| `issue` \| `dependency`. `severity`: `low` \| `med` \| `high`.

## Rapporter

| Verktyg | Parametrar | Returnerar | Roll |
|---|---|---|---|
| `pm_status_report` | `project, audience?` | `{path, commit, summary}` | reader |

- Genererar en statusrapport som fil i `<projekt>/pm/reports/STATUS-YYYY-MM-DD.md` (committas).
- `audience`: t.ex. `team` \| `ledning` — styr detaljnivå och ton (kort exekutiv vs detaljerad).

## Konventioner specifika för PM
- **Arbetsenhet = backlog-item.** PM-verktygen läser/utökar items (`estimate`, `sprint`,
  `milestone`, `depends_on`), de skapar ingen parallell datakälla.
- **Planändringar kräver `owner`** (samma princip som `backlog_set_status`). AI:n föreslår,
  människan committar.
- **Matematik i kod, narrativ av AI.** Schemaläggning, kapacitet och kritisk linje räknas
  deterministiskt; agenten förklarar och resonerar runt siffrorna.
- **Hybrid:** agenten deklarerar vilket spår (agilt/vattenfall) den följer per fråga — blandar inte.
