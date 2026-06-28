# PM-modulen — datamodell (SQLite)

Konkret schema som planeringsmotorn (`PM-PLANNING-ENGINE.md`) vilar på. SQLite (aktivt tillstånd);
git async för historik. Allt projekt-scopat; gateway tvingar RBAC; planändringar = owner.

## Relationer (översikt)
```
resource ─< resource_skill >─ skill        availability >─ resource
task ─< dependency >─ task                 task >─ milestone, skill (required)
scenario ─< scenario_change                scenario ─< allocation >─ resource, task
scenario ─< schedule >─ task               task ─< actual
```
**Bas-fakta** (resurser, uppgifter, beroenden) delas. **Plan** (allocation, schedule) är *per scenario*.
**What-if** = nytt scenario + sparse `scenario_change`-deltan ovanpå bas-fakta.

## Schema
```sql
-- RESURSER ------------------------------------------------------------------
CREATE TABLE resource (
  id INTEGER PRIMARY KEY,
  project TEXT NOT NULL,
  name TEXT NOT NULL,
  user_sub TEXT,                              -- valfri koppling till Memaix-användare (oauth_sub)
  cost_per_hour REAL,
  capacity_hours_per_day REAL NOT NULL DEFAULT 8,
  active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE skill (
  id INTEGER PRIMARY KEY, project TEXT NOT NULL, name TEXT NOT NULL
);
CREATE TABLE resource_skill (
  resource_id INTEGER NOT NULL REFERENCES resource(id),
  skill_id    INTEGER NOT NULL REFERENCES skill(id),
  level INTEGER,                              -- 1–5, valfritt
  PRIMARY KEY (resource_id, skill_id)
);
CREATE TABLE availability (                   -- semester/deltid/helg/undantag
  id INTEGER PRIMARY KEY,
  resource_id INTEGER NOT NULL REFERENCES resource(id),
  start_date TEXT NOT NULL, end_date TEXT NOT NULL,   -- ISO 8601
  hours_per_day REAL NOT NULL,               -- 0 = otillgänglig
  reason TEXT
);

-- UPPGIFTER -----------------------------------------------------------------
CREATE TABLE milestone (
  id INTEGER PRIMARY KEY, project TEXT NOT NULL,
  name TEXT NOT NULL, target_date TEXT, status TEXT NOT NULL DEFAULT 'open'
);
CREATE TABLE task (
  id INTEGER PRIMARY KEY,
  project TEXT NOT NULL,
  backlog_id TEXT,                            -- valfri koppling till backlog-item (QB-0042)
  title TEXT NOT NULL,
  estimate_hours REAL,
  required_skill_id INTEGER REFERENCES skill(id),
  priority INTEGER NOT NULL DEFAULT 3,
  milestone_id INTEGER REFERENCES milestone(id),
  status TEXT NOT NULL DEFAULT 'todo',
  percent_complete REAL NOT NULL DEFAULT 0
);
CREATE TABLE dependency (                     -- DAG
  predecessor_id INTEGER NOT NULL REFERENCES task(id),
  successor_id   INTEGER NOT NULL REFERENCES task(id),
  type TEXT NOT NULL DEFAULT 'FS',            -- FS/SS/FF/SF
  lag_days REAL NOT NULL DEFAULT 0,
  PRIMARY KEY (predecessor_id, successor_id)
);

-- SCENARIER & PLAN ----------------------------------------------------------
CREATE TABLE scenario (
  id INTEGER PRIMARY KEY, project TEXT NOT NULL,
  name TEXT NOT NULL,
  kind TEXT NOT NULL,                         -- baseline | committed | whatif
  parent_id INTEGER REFERENCES scenario(id),
  created TEXT NOT NULL,
  committed_by TEXT,                          -- owner som godkände (audit)
  note TEXT
);
CREATE TABLE scenario_change (                -- what-if-deltan mot bas-fakta
  id INTEGER PRIMARY KEY,
  scenario_id INTEGER NOT NULL REFERENCES scenario(id),
  entity TEXT NOT NULL,                       -- task | dependency | resource | availability
  entity_id INTEGER NOT NULL,
  field TEXT NOT NULL,
  value TEXT                                  -- nytt värde (text-serialiserat)
);
CREATE TABLE allocation (                     -- motorns utdata: vem gör vad när (per scenario)
  id INTEGER PRIMARY KEY,
  scenario_id INTEGER NOT NULL REFERENCES scenario(id),
  task_id     INTEGER NOT NULL REFERENCES task(id),
  resource_id INTEGER NOT NULL REFERENCES resource(id),
  start_date TEXT NOT NULL, end_date TEXT NOT NULL, hours REAL NOT NULL
);
CREATE TABLE schedule (                       -- beräknat schema/kritisk linje (per scenario)
  scenario_id INTEGER NOT NULL REFERENCES scenario(id),
  task_id     INTEGER NOT NULL REFERENCES task(id),
  earliest_start TEXT, earliest_finish TEXT,
  latest_start TEXT,   latest_finish TEXT,
  slack_days REAL, is_critical INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (scenario_id, task_id)
);

-- UPPFÖLJNING ---------------------------------------------------------------
CREATE TABLE actual (                         -- tidlogg/framdrift
  id INTEGER PRIMARY KEY,
  task_id INTEGER NOT NULL REFERENCES task(id),
  date TEXT NOT NULL, hours_logged REAL, percent_complete REAL, note TEXT
);

CREATE INDEX ix_task_project ON task(project);
CREATE INDEX ix_alloc_scn ON allocation(scenario_id);
CREATE INDEX ix_sched_scn ON schedule(scenario_id);
CREATE INDEX ix_actual_task ON actual(task_id);
```

## Hur motorn använder schemat
- **`allocate(scenario)`** — läs bas-fakta + scenariots `scenario_change`-deltan → kör schemaläggaren →
  skriv `allocation` + `schedule` för scenariot. (Heuristik i v1, OR-Tools CP-SAT senare.)
- **`whatif(base, changes)`** — skapa `scenario(kind='whatif', parent_id=base)`, lägg `scenario_change`-
  rader, kör `allocate`, **diffa** `schedule`/`allocation` mot parent → konsekvensanalys.
- **`commit(scenario)`** — markera som `committed` (owner → `committed_by`); frys en kopia som
  `kind='baseline'` för variansreferens.
- **`variance(project)`** — jämför baseline-scenariots `schedule`/`allocation` mot `actual` → slippage,
  över-/underbelastning, framdrift.
- **`utilization(resource, period)`** — summera `allocation.hours` per resurs/period mot kapacitet
  (`resource.capacity_hours_per_day` − `availability`-undantag).

## Noteringar
- **Projekt-scopning:** varje rad bär `project` (direkt eller via FK). Gateway filtrerar per användarens
  grant; en extern konsult ser bara sitt projekts resurser/uppgifter.
- **Bas-fakta vs plan:** uppgifter/resurser/beroenden är "sanningen"; allocation/schedule är "planen"
  per scenario → en what-if rör aldrig den committade planen.
- **Historik:** SQLite är aktivt tillstånd; git async snapshottar (DB-dump eller markdown-export) för
  rollback (SAFETY.md).
- **Audit:** `scenario.committed_by` + audit-loggen visar vem som godkände vilken plan.

## Acceptanskriterier
- [ ] Resurser har kapacitet, tillgänglighet (undantag) och kompetenser.
- [ ] Uppgifter har estimat, beroenden (DAG, ingen cykel), ev. krävd kompetens och milstolpe.
- [ ] What-if skapar isolerat scenario med deltan; rör inte committed plan.
- [ ] `allocate` skriver allocation+schedule deterministiskt; kritisk linje markeras.
- [ ] `variance` jämför baseline mot actuals; `utilization` mot kapacitet.
- [ ] Allt projekt-scopat; commit kräver owner och loggas.
