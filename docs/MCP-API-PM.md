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

## Planeringsmotor — resurser, allokering, konsekvens
Se `PM-PLANNING-ENGINE.md` + `PM-DATA-MODEL.md`. Beräkning sker i kod; LLM tolkar, räknar aldrig.

| Verktyg | Parametrar | Returnerar | Roll |
|---|---|---|---|
| `pm_resource_add` | `project, name, capacity_hours_per_day?, cost_per_hour?, skills?[]` | `{id}` | collaborator |
| `pm_resource_list` | `project` | `[{id, name, capacity, skills, active}]` | reader |
| `pm_resource_availability` | `project, resource, start, end, hours_per_day, reason?` | `{id}` | collaborator |
| `pm_task_upsert` | `project, title, estimate_hours?, required_skill?, priority?, milestone?, depends_on?[], backlog_id?, id?` | `{id}` | collaborator |
| `pm_log_actual` | `project, task, date, hours?, percent_complete?, note?` | `{ok}` | collaborator |
| `pm_allocate` | `project, scenario?` | `{scenario, allocations:[{task, resource, start, end, hours}], critical_path:[task], finish_date, conflicts:[{resource, period, overload_hours}]}` | **owner** |
| `pm_whatif` | `project, base?, changes:[{entity, id, field, value}]` | `{scenario, diff:{finish_delta_days, milestone_impact:[{milestone, delta_days}], new_conflicts, critical_changes:[task]}}` | reader |
| `pm_commit_plan` | `project, scenario` | `{committed, baseline_id}` | **owner** |
| `pm_variance` | `project` | `{tasks:[{task, planned_finish, percent_complete, slippage_days}], over_allocated:[{resource, period}], summary}` | reader |
| `pm_utilization` | `project, start, end` | `[{resource, period, allocated_hours, capacity_hours, pct}]` | reader |

- **`pm_allocate`** kör schemaläggaren (RCPSP-heuristik → OR-Tools CP-SAT) → skriver `allocation` +
  `schedule` för scenariot; `conflicts` = resursöverbelastning (allokerat > kapacitet) per period.
- **`pm_whatif`** skapar ett isolerat `whatif`-scenario (rör ej committed plan), applicerar `changes`
  (`entity`: task|dependency|resource|availability), kör motorn och **diffar mot parent**.
- **`pm_commit_plan`** kräver owner; fryser en `baseline` för variansreferens.
- **`pm_variance`** jämför baseline mot `actual` (slippage, överbelastning); **`pm_utilization`**
  jämför allokerade timmar mot kapacitet.

## Konventioner specifika för PM
- **Arbetsenhet = backlog-item.** PM-verktygen läser/utökar items (`estimate`, `sprint`,
  `milestone`, `depends_on`), de skapar ingen parallell datakälla.
- **Planändringar kräver `owner`** (samma princip som `backlog_set_status`). AI:n föreslår,
  människan committar.
- **Matematik i kod, narrativ av AI.** Schemaläggning, kapacitet och kritisk linje räknas
  deterministiskt; agenten förklarar och resonerar runt siffrorna.
- **Hybrid:** agenten deklarerar vilket spår (agilt/vattenfall) den följer per fråga — blandar inte.
