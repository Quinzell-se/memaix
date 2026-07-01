# Funktion #4 — Stående instruktioner & automationsregler

SPDX-License-Identifier: AGPL-3.0-or-later

Designdok + byggspec för att låta Memaix arbeta *mellan* sessionerna: användaren
säger en gång *"när det kommer ett mejl från kunden, skapa ett backlog-item och
ta upp det i briefen"* — och assistenten fortsätter göra det. Två lager:
**deterministiska regler** som körs server-side, och **stående instruktioner** i
klarspråk som den kopplade AI-klienten plockar upp vid sessionsstart.

Byggs stegvis enligt [Byggordning](#byggordning) och
[Utvecklingsinstruktioner](#utvecklingsinstruktioner).

---

## 1. Vad användaren upplever

- **Regel:** *"När mejl från `@kund.se` kommer → skapa backlog-item i projekt X och
  notifiera mig."* Skapas en gång (via verktyg eller board), listas och kan stängas
  av. Körs sedan automatiskt utan att användaren är närvarande.
- **Stående instruktion:** *"Sammanfatta alltid långa mejl innan du visar dem",
  "skriv kort och på svenska".* Lagras och injiceras i assistentens kontext när
  användaren öppnar Memaix — guidning som modellen följer, inte server-automation.

Det förvandlar Memaix från något man styr per anrop till något som jobbar åt en.

---

## 2. Nyckelbeslut

1. **Två distinkta lager.**
   - *Deterministiska regler* körs i gatewayen, utan AI, reproducerbart.
   - *Stående instruktioner* är text som exponeras till klienten (resource/prompt)
     — modellen tolkar dem. De utför aldrig något själva.
2. **Triggers kommer inifrån, inte från connectorn** (MCP kan inte pusha, funktion
   #1 §1). Källor: schemalagt (återanvänd schedulern från #1), poll av mail,
   inkommande webhooks, samt interna skriv-händelser (audit-hook från #2/#3).
3. **Åtgärder återanvänder verktygen.** En regel-åtgärd anropar samma
   tool-funktioner (backlog_add, memory_append, email_create_draft, notify…).
   **Utgående åtgärder går alltid genom utkorgen (funktion #3)** — en regel får
   aldrig skicka mejl utan godkännande om projektet är i `review`.
4. **Idempotent exekvering.** Varje (regel, utlösande händelse) körs högst en gång
   (dedupe-nyckel), så mail-poll eller retry inte dubbelutlöser (gap #13).
5. **Säkert som default.** Regler körs med initierarens ACL-roll; en regel kan
   aldrig göra mer än användaren själv får. Nya regler som gör utgående åtgärder
   kräver `owner`.

---

## 3. Översikt

```
  Triggerkällor
   ├─ schedule   (scheduler från #1: cron-liknande)
   ├─ mail-poll  (per projekt-mailbox, intervall)
   ├─ webhook    (POST /hooks/{token} — signerad, inkommande)
   └─ internal   (audit-hook: backlog/memory/pm-skrivning)
        │  Event{type, project, payload}
        ▼
  RuleEngine.evaluate(event)
        │  matcha regler (enabled, project, when-villkor)
        │  dedupe (rule_id + event_key)  → hoppa om redan körd
        ▼
  för varje matchande regel: kör actions i ordning
        ├─ backlog_add / memory_append / pm_raid_add …   (direkt)
        └─ email_send / calendar_create …  →  utkorg (#3)  (kräver godkänn)
        │
        ▼
  logga körning (rule_runs) + audit
```

Stående instruktioner (separat, enkelt): text per användare → MCP-resource
`memaix://standing-instructions` + injektion i `onboarding`/sessions-prompt.

---

## 4. Datamodell

Ny SQLite-DB via env `MEMAIX_RULES_DB` (default `/tmp/memaix-rules.db`).

```sql
CREATE TABLE IF NOT EXISTS rules (
    id          TEXT PRIMARY KEY,        -- uuid4 hex
    memaix_user TEXT NOT NULL,           -- ägare (körs med dennes roll)
    project     TEXT NOT NULL,
    name        TEXT NOT NULL,
    enabled     INTEGER NOT NULL DEFAULT 1,
    trigger     TEXT NOT NULL,           -- JSON: {type, ...}
    conditions  TEXT NOT NULL DEFAULT '[]',  -- JSON: [{field, op, value}]
    actions     TEXT NOT NULL,           -- JSON: [{type, params}]
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rule_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id     TEXT NOT NULL,
    event_key   TEXT NOT NULL,           -- idempotens: rule_id + händelse-id
    ran_at      TEXT NOT NULL,
    ok          INTEGER NOT NULL,
    detail      TEXT NOT NULL DEFAULT '',
    UNIQUE(rule_id, event_key)
);

CREATE TABLE IF NOT EXISTS standing_instructions (
    memaix_user TEXT PRIMARY KEY,
    text        TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
```

### Trigger-typer (v1)
```json
{"type": "schedule", "cron": "0 8 * * 1-5"}          // vardagar 08:00 (användarens tz)
{"type": "mail", "project": "acme", "from_contains": "@kund.se", "subject_contains": ""}
{"type": "webhook", "token": "<slumpad>"}            // POST /hooks/{token}
{"type": "internal", "event": "backlog.status", "to": "done"}
```

### Villkor (conditions) — enkel DSL
`{"field": "subject", "op": "contains|equals|matches", "value": "faktura"}`.
Alla villkor måste vara sanna (AND). `field` slår mot event.payload.

### Åtgärds-typer (actions)
```json
{"type": "backlog_add",     "params": {"project": "acme", "title_from": "subject", "description_from": "body"}}
{"type": "memory_append",   "params": {"project": "acme", "note": "inbox-log.md", "text_from": "summary"}}
{"type": "pm_raid_add",     "params": {...}}
{"type": "notify",          "params": {"text_from": "subject"}}       // via funktion #1-kanaler
{"type": "email_draft",     "params": {...}}                          // säkert (utkast)
{"type": "email_send",      "params": {...}}                          // → utkorg (#3)
```
`*_from`-fält mappar från event.payload; annars literala `*`-fält.

---

## 5. Regelmotor

`rules/engine.py`:

```python
def evaluate(engine_ctx, event: dict) -> list[dict]:
    """Hitta matchande regler för event, kör deras actions, returnera körresultat."""
```

Flöde:
1. Hämta `enabled` regler för `event.project` (och globala om vi tillåter).
2. Matcha `trigger.type == event.type` + trigger-specifika fält + `conditions`.
3. **Dedupe:** `event_key = event['id']`; hoppa om `(rule_id, event_key)` finns i
   `rule_runs`. Reservera raden *innan* körning (compare-and-set/INSERT OR IGNORE).
4. Kör `actions` i ordning via en **action-dispatch** som anropar tool-funktioner
   med regelägarens `acl`+`user`. Utgående åtgärder passerar utkorgen automatiskt
   (samma gate som #3; sätt aldrig `_confirmed`).
5. Logga `rule_runs` (ok/detalj) + audit (`tool=f"rule:{rule_id}"`).

Motorn är ren nog att testas utan trigger-källor: mata in ett `event` och
verifiera actions.

---

## 6. Triggerkällor

- **schedule** — schedulern från funktion #1 utökas: förutom briefer läser den
  `rules` med `trigger.type=='schedule'`, evaluerar cron mot användarens tz, och
  skickar ett `{type:'schedule', id: f"{rule_id}:{YYYY-MM-DD-HH}"}`-event.
- **mail** — en poll-loop (samma scheduler) hämtar nya meddelanden per mailbox
  (spåra senaste sedda UID per projekt) och skickar `{type:'mail', project, id:
  f"{project}:{uid}", payload:{from,subject,body,…}}`.
- **webhook** — ny route `POST /hooks/{token}` i gatewayen; slår upp regeln på
  `token`, verifierar HMAC-signatur (delad hemlighet), skickar `{type:'webhook',
  id: request-id, payload: json}`. Inkommande integration (formulär → backlog).
- **internal** — en hook i audit/skrivvägarna (från #2/#3) publicerar
  `{type:'internal', event:'backlog.status', payload:{id,from,to}}`.

Alla källor konvergerar till `evaluate(event)`. Bygg källorna sist; motorn först.

---

## 7. MCP-yta, board och stående instruktioner

Verktyg i `server.py` (via `_tool_call`, projekt-scope):

| Verktyg | Signatur | Roll |
|---------|----------|------|
| `rule_add` | `(project, name, trigger: dict, actions: list, conditions: list=[])` | owner om någon action är utgående, annars collaborator |
| `rule_list` | `(project: str\|None=None)` | reader (synliga projekt) |
| `rule_set_enabled` | `(rule_id, enabled: bool)` | owner |
| `rule_delete` | `(rule_id)` | owner |
| `rule_test` | `(rule_id, sample_event: dict)` | owner — torrkör mot ett exempel-event, utför inget |
| `standing_set` | `(text: str)` | valfri roll (per användare) |
| `standing_get` | `()` | — |

Validera `trigger`/`actions`/`conditions` mot kända typer vid `rule_add`
(avvisa okända). `rule_test` kör motorn med `dry_run=True` (actions loggas men
utförs inte) — viktigt för att användaren ska våga skapa regler.

**Board:** en "Automation"-vy som listar regler, visar senaste körningar
(`rule_runs`) och togglar enabled. **Stående instruktioner** exponeras som MCP-
resource `memaix://standing-instructions/{user}` och vävs in i
`onboarding`/sessions-prompten så modellen ser dem.

---

## 8. Säkerhet & integritet

- **Regler körs med ägarens roll.** Action-dispatch använder regelns `memaix_user`
  + `acl`; kan aldrig eskalera. Utgående actions → utkorgen (#3), aldrig direkt.
- **Webhook-endpoints signeras** (HMAC med per-regel-hemlighet); avvisa osignerat.
  Rate-limita `/hooks/{token}`.
- **Idempotens** hindrar dubbelutlösning vid mail-poll/retry.
- **Regel-innehåll är data.** Mail som triggar en regel kan innehålla
  injektionsförsök; regelmotorn tolkar bara deklarativa fält (from/subject/…),
  aldrig fri text som instruktion. AI-genererat innehåll (t.ex. `summary`) skapas
  bara om en action uttryckligen ber om det, och utgående resultat går via utkorgen.
- **Loggning:** `rule_runs` + audit, aldrig hemligheter eller full mailbody.
- **Avstängning:** `rule_set_enabled(false)` stoppar direkt; koppla till kill-switch
  (OPEN-GAPS #6) så att avstängt konto slutar utlösa regler.

---

## Byggordning

1. **RulesStore** (`rules/store.py`) — SQLite (rules, rule_runs, standing). *Isolerat.*
2. **Matchning + villkor** (`rules/match.py`) — trigger-match + conditions-DSL.
3. **Action-dispatch** (`rules/actions.py`) — mappa action→tool, `*_from`-mappning.
4. **Engine** (`rules/engine.py`) — evaluate med dedupe + dry_run.
5. **MCP-yta** (`server.py`) — rule_* + standing_* + resource.
6. **Triggerkällor** — schedule + mail-poll (via #1-scheduler); webhook-route; internal-hook.
7. **Board** — automation-vy.
8. **Config + docs.**
9. **CI** — grönt.

---

## Utvecklingsinstruktioner

Konventioner: se funktion #1-doket. Kör `python -m pytest -q` från `gateway/`.
Bygg motorn (steg 1–4) helt testbar innan triggerkällorna (steg 6).

### Steg 1 — `rules/store.py`
Paket `rules/__init__.py` + `RulesStore` med CRUD för `rules`, `standing_instructions`
och `rule_runs`. Dedupe-reservation: `try_reserve(rule_id, event_key) -> bool`
via `INSERT OR IGNORE ... RETURNING`/rowcount. **Test** (`tests/test_rules_store.py`):
CRUD; `list` filtrerar på projekt/enabled; `try_reserve` True första, False andra;
standing set/get.

### Steg 2 — `rules/match.py`
`trigger_matches(trigger, event) -> bool` och `conditions_pass(conditions, payload)
-> bool` (ops: contains/equals/matches). **Test** (`tests/test_rules_match.py`):
mail from/subject-match; internal status-övergång; conditions AND; okänd op → False.

### Steg 3 — `rules/actions.py`
`run_action(acl, user, action, payload, *, tools=None, dry_run=False) -> dict`.
`_resolve_params` mappar `*_from` mot payload. Dispatch-tabell action→callable
(backlog_add, memory_append, pm_raid_add, email_create_draft, email_send,
notify). Utgående (email_send) anropas **utan** `_confirmed` (→ utkorg). `dry_run`
loggar men utför inte. **Test** (`tests/test_rules_actions.py`): backlog_add
skapar item med titel från subject; email_send i review-läge → pending (utkorg);
dry_run utför inget.

### Steg 4 — `rules/engine.py`
`evaluate(store, acl, event, *, tools=None, dry_run=False) -> list[dict]`:
hämta matchande regler, dedupe via `try_reserve` (hoppa om ej dry_run och redan
körd), kör actions, logga `rule_runs`. **Test** (`tests/test_rules_engine.py`):
matchande regel kör sina actions; dedupe hindrar andra körningen för samma
event_key; icke-matchande regel hoppas; en action-fel fäller inte de andra
(logga, fortsätt) och markeras i detail.

### Steg 5 — MCP-yta i `server.py`
Lat `_get_rules()`. Verktygen `rule_add` (validera typer, owner om utgående
action), `rule_list`, `rule_set_enabled`, `rule_delete`, `rule_test` (dry_run),
`standing_set/get`, samt resource `memaix://standing-instructions`. **Test**
(`tests/test_server.py`): add→list→toggle→delete; `rule_add` med okänd
action-typ avvisas; `rule_test` utför inget men returnerar plan.

### Steg 6 — Triggerkällor
- Utöka schedulern (#1) att även läsa schedule-regler och maila-poll (spåra
  senaste UID per projekt i en liten tabell). 
- Ny route `POST /hooks/{token}` i `server.py`/board-routes med HMAC-verifiering.
- Internal-hook: en `publish_event(event)` som audit-skrivvägen anropar.
**Test:** mail-poll bygger rätt event av en injicerad mailbox och kör motorn en
gång per nytt UID; webhook avvisar felaktig signatur; schedule-cron matchar rätt
timme i tz (deterministiskt `now`).

### Steg 7 — Board
Automation-vy: `GET /board/api/rules`, `POST /board/api/rules/{id}` (toggle),
lista `rule_runs`. Enforce owner för mutationer.

### Steg 8 — Config + docs
`memaix.example.yaml`: `rules.mail_poll_interval`, webhook-bas-URL. Registrera
doket i `docs/INDEX.md` (gjort); uppdatera `DEVELOPMENT-PROPOSALS.md`.

### Steg 9 — Kör allt
`cd gateway && python -m pytest -q` + `python3 scripts/check-docs-index.py`.

### Acceptanskriterier
- [ ] `rule_add` skapar en regel; ett matchande mail-event kör dess actions exakt en gång (dedupe verifierad).
- [ ] Utgående action (email_send) hamnar i utkorgen (#3) — regeln skickar aldrig utan godkännande i review-läge.
- [ ] `rule_test` torrkör mot ett exempel-event utan att utföra något.
- [ ] Regel körs med ägarens roll; kan inte göra mer än användaren själv får.
- [ ] Webhook `/hooks/{token}` avvisar osignerade anrop; mail-poll dubbelutlöser inte.
- [ ] Stående instruktioner nås via resource och injiceras i sessions-prompten.
- [ ] `rule_set_enabled(false)` stoppar utlösning; inga hemligheter/mailbody i loggar; hela sviten + docs-index grön.

---

## Framtida arbete
- Naturspråk → regel: låt klienten föreslå en regel-JSON som användaren bekräftar.
- Fler triggers (kalender "möte om 15 min", filändring i vault).
- Åtgärds-kedjor med villkorlig gren (if/else) och variabler.
- Delade team-regler (inte bara per användare) med tydligt ägarskap.
- Torrkörnings-historik och "vad skulle den här regeln ha gjort senaste veckan".
