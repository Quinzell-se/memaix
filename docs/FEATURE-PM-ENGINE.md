# Funktion #9 — PM-planeringsmotor & agent (byggspec)

SPDX-License-Identifier: AGPL-3.0-or-later

Byggspec som **realiserar** designen i [PM-PLANNING-ENGINE.md](PM-PLANNING-ENGINE.md)
och schemat i [PM-DATA-MODEL.md](PM-DATA-MODEL.md), och lägger ett agent-lager
ovanpå. Detta dok upprepar inte designen — det säger *hur* den byggs, i vilken
ordning, med signaturer, testkrav och acceptanskriterier.

Fas 4 i [ROADMAP.md](ROADMAP.md) — kan byggas **parallellt** med fas 2–3 eftersom
motorn är fristående. Följ determinismgränsen i [PM-AGENT.md](PM-AGENT.md):
**motorn räknar, LLM:en förklarar — LLM:en räknar aldrig.**

---

## 1. Kärnprincip (helig)

De svåra förmågorna (schemaläggning, kritisk linje, kapacitet, datum) är
**deterministiska beräkningsproblem** och byggs i kod. LLM:en (a) fångar avsikt →
strukturerad input, (b) förklarar motorns resultat, (c) flaggar risk, (d) skriver
rapporter. **Owner committar planändringar.**

## 2. Arkitektur

```
  pm_* (nuvarande) + nya resource_*/task_*/allocate/whatif/variance/utilization/report
        │  (MCP-verktyg via _tool_call, RBAC: planändring = owner)
        ▼
  PM-motor (ren kod, deterministisk)
   ├─ schedule.py   forward/backward pass → earliest/latest, slack, kritisk linje
   ├─ allocate.py   resursbegränsad list-scheduling-heuristik (v1) → allocation
   ├─ whatif.py     klona scenario + deltan → kör om → diffa mot baseline
   └─ report.py     rollups: utnyttjande, burndown, milstolpe, RAID, varians
        │
        ▼
  PMStore (SQLite, schema = PM-DATA-MODEL.md)  — bas-fakta delas, plan per scenario
```

## 3. Datamodell

Exakt schemat i [PM-DATA-MODEL.md](PM-DATA-MODEL.md): `resource`, `skill`,
`resource_skill`, `availability`, `milestone`, `task`, `dependency`, `scenario`,
`scenario_change`, `allocation`, `schedule`, `actual`. Ny SQLite-DB via env
`MEMAIX_PM_DB` (default `/tmp/memaix-pm.db`), projekt-scopat. Git-async snapshot för
historik (SAFETY.md). Tid normaliserad till UTC (OPEN-GAPS #16).

## 4. Motorn — deterministiska kärnor

- **Kritisk linje** (`schedule.py`): topologisk sortering av `task`+`dependency`
  (DAG, avvisa cykler), forward pass (earliest start/finish från estimat+beroenden+
  lag), backward pass (latest start/finish från projektslut), `slack = latest-earliest`,
  `is_critical = slack==0`. Ren grafmatematik, exakt.
- **Allokering** (`allocate.py`): prioritetsbaserad list-scheduling-heuristik v1 —
  sortera på prioritet + kritikalitet, placera varje uppgift på tidigast möjliga
  resurs som (a) har krävd kompetens, (b) har ledig kapacitet (kapacitet −
  availability-undantag − redan allokerat), (c) respekterar beroenden. Skriv
  `allocation` + `schedule`. Uppgradering till OR-Tools CP-SAT dokumenteras men är
  inte v1.
- **What-if** (`whatif.py`): skapa `scenario(kind='whatif', parent_id=base)`, lägg
  `scenario_change`-deltan, kör `allocate`, **diffa** `schedule`/`allocation` mot
  parent → kritisk linje-ändring, milstolpsförskjutning, resurskonflikter.
- **Uppföljning** (`report.py`): `variance` (baseline vs `actual` → slippage),
  `utilization` (allocation-timmar mot kapacitet/period), burndown, milstolpstatus.

Allt rent och testbart utan LLM — mata in fixtures, verifiera siffror.

## 5. MCP-verktyg (utöka `pm_*`)

Alla projekt-scopade via `_tool_call`; RBAC per PM-AGENT.md (planändring = owner).

| Verktyg | Roll | Beskrivning |
|---------|------|-------------|
| `resource_add` / `resource_list` / `resource_availability` | owner / reader / owner | Resurser, kapacitet, kompetens, undantag. |
| `task_estimate` / `task_assign` | collaborator / owner | Estimat & (manuell) tilldelning. |
| `allocate(scenario)` | owner | Kör motorn → allocation + schedule. |
| `whatif(base, changes)` | collaborator | Simulera scenario, returnera diff. |
| `utilization(resource?, period)` | reader | Utnyttjandegrad. |
| `variance()` | reader | Plan vs utfall. |
| `pm_report(kind, audience)` | reader | Rollup-data för LLM att formulera. |
| `plan_commit(scenario)` | owner | Markera committed + frys baseline (audit: `committed_by`). |

Verktygen returnerar **strukturerad data + siffror**; LLM:en formulerar narrativet.
Koppla `task.backlog_id` ↔ backlog-item så PM och backlog hänger ihop.

## 6. Agent-lager (LLM:ens roll)

MCP-prompter som guidar assistenten att använda motorn rätt:
- `pm_plan_session(project)` — dekomponera mål → uppgifter (föreslå estimat/beroenden),
  fånga resurser/tillgänglighet i klarspråk → `resource_*`/`task_*`, kör `allocate`,
  **förklara** resultat och flagga risk. Owner committar.
- `pm_whatif_session(project)` — hjälp användaren formulera en fråga ("om vi tappar
  Anna 2 veckor"), översätt till `changes`, kör `whatif`, förklara diffen.
- `pm_review(project)` (finns) — utöka med `variance`/`utilization`/kritisk linje.

LLM:en räknar aldrig; den översätter avsikt → verktygsanrop och resultat → språk.

## 7. Säkerhet & integritet

- **Projekt-scopning:** varje rad bär `project`; gatewayen filtrerar per grant (en
  extern konsult ser bara sitt projekts resurser/uppgifter).
- **Planändring = owner**, loggas (`scenario.committed_by` + audit).
- **What-if rör aldrig committed plan** (isolerade scenarier).
- **Gissa aldrig datum** — flagga saknade estimat/tillgänglighet som osäkerhet i
  outputen istället för att hitta på (PM-PLANNING-ENGINE.md "ärligt om begränsningar").

## Byggordning (följer PM-PLANNING-ENGINE.md §Faser)

1. **PMStore + schema** (PM-DATA-MODEL.md) + **kritisk linje** + `utilization`-rapport.
2. **Kapacitetsbaserad allokering** (heuristik) + **baseline** + **varians**.
3. **What-if-scenarier** + diff-rapport.
4. **CP-SAT-optimering** (OR-Tools) för tyngre allokering/leveling.
5. **Rapportpaket** per publik (team/ledning) + agent-prompter.
6. **CI** — grönt.

---

## Utvecklingsinstruktioner

Konventioner: se [FEATURE-PROACTIVE-BRIEF.md](FEATURE-PROACTIVE-BRIEF.md). Motorn
byggs **ren och testbar först** (steg 1–3) före MCP-ytan. Kör `python -m pytest -q`
från `gateway/`. OR-Tools (steg 4) är ett **valfritt extra** i `pyproject.toml`
(`[project.optional-dependencies] pm = ["ortools"]`) så basinstallen förblir lätt.

### Steg 1 — `pm/store.py` (schema)
Paket `pm/__init__.py` + `PMStore.for_path(db_path)` som skapar hela schemat i
PM-DATA-MODEL.md. CRUD för resource/skill/availability/task/dependency/milestone/
scenario/scenario_change/allocation/schedule/actual. **Test** (`tests/test_pm_store.py`):
skapa resurser/uppgifter/beroenden; `dependency` avvisar cykel; projekt-scopad läsning.

### Steg 2 — `pm/schedule.py` (kritisk linje)
`compute_schedule(tasks, deps, calendar) -> list[ScheduleRow]`: topologisk sortering
(fel vid cykel), forward/backward pass, slack, `is_critical`. Ren funktion.
**Test** (`tests/test_pm_schedule.py`): känd graf → rätt earliest/latest/slack;
kritisk linje = längsta vägen; cykel → tydligt fel; lag_days respekteras.

### Steg 3 — `pm/allocate.py` + `pm/report.py`
`allocate(store, scenario)` (list-scheduling-heuristik enligt §4) → skriv allocation+
schedule. `utilization(...)`, `variance(...)` i `report.py`. **Test**
(`tests/test_pm_allocate.py`): allokering respekterar kapacitet + kompetens +
beroenden; överbokning undviks; `utilization` summerar rätt mot kapacitet −
availability; `variance` jämför baseline mot actuals.

### Steg 4 — `pm/whatif.py`
`whatif(store, base_scenario, changes) -> diff`: klona scenario, lägg
`scenario_change`, kör `allocate`, diffa schedule/allocation mot parent. **Test**
(`tests/test_pm_whatif.py`): ta bort en resurs → milstolpe skjuts, kritisk linje
ändras, committed baseline orörd; diffen pekar ut påverkade uppgifter.

### Steg 5 — MCP-yta i `server.py`
Lat `_get_pm()`. Verktygen i §5 via `_tool_call` (planändring enforce:ar owner).
`plan_commit` sätter `committed_by` + fryser baseline. **Test** (`tests/test_server.py`):
resource_add→task_estimate→allocate→utilization-flöde; `whatif` returnerar diff utan
att röra committed; reader nekas `allocate`/`plan_commit`.

### Steg 6 — Agent-prompter
`pm_plan_session`, `pm_whatif_session`; utöka `pm_review`. Prompterna instruerar
LLM:en att **aldrig räkna själv** utan kalla motorn och förklara. **Test:** prompt-
strängar innehåller determinismgräns-instruktionen och rätt verktygsordning.

### Steg 7 — (valfritt) CP-SAT
`pm/allocate_cpsat.py` bakom `pm`-extran; välj heuristik/CP-SAT via config. **Test**
hoppas om `ortools` saknas (`pytest.importorskip`).

### Steg 8 — Config + docs
`memaix.example.yaml`: `pm.allocator: heuristic|cpsat`. Registrera doket i
`docs/INDEX.md` (gjort); länka från PM-PLANNING-ENGINE.md/ADDON-PM-BUILD.md.

### Steg 9 — Kör allt
`cd gateway && python -m pytest -q` + `python3 scripts/check-docs-index.py`.

### Acceptanskriterier (speglar PM-PLANNING-ENGINE.md)
- [ ] Resurser modelleras med kapacitet, tillgänglighet och kompetens.
- [ ] Allokering respekterar kapacitet + kompetens + beroenden, deterministiskt.
- [ ] Kritisk linje beräknas exakt (forward/backward pass); cykler avvisas.
- [ ] What-if visar konsekvens (kritisk linje/milstolpe/konflikter) diffad mot baseline, utan att röra committed plan.
- [ ] Uppföljning visar varians plan vs utfall; utnyttjandegrad mot kapacitet.
- [ ] All beräkning i kod; LLM endast gränssnitt; `plan_commit` kräver owner och loggas.
- [ ] Saknade estimat/tillgänglighet flaggas som osäkerhet — inga gissade datum; hela sviten + docs-index grön.

---

## Framtida arbete
- CP-SAT-optimering med resursutjämning och kostnadsminimering.
- Monte-Carlo-prognos av slutdatum från historisk velocity (osäkerhetsintervall).
- Portfölj-vy: beroenden och resursdelning *mellan* projekt.
- Möte → plan: transkript (connector) → uppgifter/estimat-förslag som owner granskar.
- Auto-triage av backlog (föreslå value/complexity/risk) kopplat till `task`-estimat.
