# Funktion #5 — Ångra & åtgärdstidslinje

SPDX-License-Identifier: AGPL-3.0-or-later

Designdok + byggspec för en tidslinje över allt assistenten *gjort* — skapade
händelser, utkast, minnesskrivningar, flyttade kort — med **ångra** på varje rad.
Reversibilitet är förtroendets grund: när misstag är billiga att rätta vågar
användaren släppa fram assistenten mer, vilket förstärker funktion #1–#4.

Byggs stegvis enligt [Byggordning](#byggordning) och
[Utvecklingsinstruktioner](#utvecklingsinstruktioner).

---

## 1. Vad användaren upplever

En tidslinje (i board:en och via verktyg): *"14:02 skapade kalenderhändelse
'Möte med X'", "13:50 skrev minnesnot `standup/2026-07-01.md`", "13:44 flyttade
kort a1b2c3d4 → done"*. Varje rad har **Ångra**. Skapade AI:n fel
kalenderhändelse? Ett klick tar bort den. Skrev fel i minnet? Ett klick återställer
förra versionen.

Det gör assistentens skrivande åtgärder trygga att prova — och kompletterar
utkorgen (#3): utkorgen stoppar *utgående* saker *före*, tidslinjen ångrar
*interna* saker *efter*.

---

## 2. Nyckelbeslut

1. **En åtgärds-logg med inversa operationer.** Varje skrivande verktygsanrop
   registrerar ett `action`-record med tillräckligt för att invertera det (t.ex.
   för `calendar_create`: event-id → invers = `calendar_delete(id)`; för
   `memory_write`: commit-hash → invers = `git revert`/återställ förra innehållet).
2. **Bygg på det som redan finns.** Audit-loggen ger *att* något hänt; den här
   funktionen lägger till *hur man ångrar det*. Minne/backlog har redan git/
   version — återanvänd det (`memory_revert`, backlog-version).
3. **Ångra är i sig en åtgärd** som loggas (så man kan "ångra ångra"/se historik),
   men markeras som `undo_of=<action_id>` och är inte själv ångringsbar i v1.
4. **Ärlig om det som inte går att ångra.** Ett skickat mejl kan inte återkallas —
   tidslinjen visar det som `irreversible` med förklaring (och pekar på utkorgen
   #3 som rätt ställe att stoppa det *innan* sändning). Utkast kan raderas.
5. **Idempotent & säkert.** En åtgärd kan ångras högst en gång (status-lås); ångra
   kräver samma roll som den ursprungliga åtgärden och samma projekt-ACL.

---

## 3. Reversibilitet per verktyg

| Åtgärd | Registreras | Ångra (invers) | Klass |
|--------|-------------|----------------|-------|
| `memory_write`/`append` | commit-hash (finns) | `memory_revert(commit)` (finns) | reversibel |
| `backlog_set_status`/`score`/`comment` | föregående `version` + fält | skriv tillbaka tidigare värde (optimistisk låsning) | reversibel |
| `backlog_add` | nytt id | markera `rejected`/radera item | reversibel |
| `board_move` (status via board) | gammal status (finns i `_old_status`) | sätt tillbaka gammal status | reversibel |
| `calendar_create` | event-id | `calendar_delete(id)` | reversibel |
| `calendar_update` | fält före ändring | skriv tillbaka tidigare fält | reversibel |
| `email_create_draft` | draft-referens | radera utkast | reversibel |
| `email_send` | — | **går ej** att återkalla | `irreversible` |
| `pm_plan_sprint` | sprint-fil + stämplade items | ta bort sprint + avstämpla | reversibel |

Registret sparar en **invers-spec** (`inverse` JSON) så ångra inte behöver
gissa: `{tool, args}` som körs för att invertera.

---

## 4. Datamodell

Ny SQLite-DB via env `MEMAIX_ACTIONS_DB` (default `/tmp/memaix-actions.db`).
(Kan även samlokaliseras med audit-DB:n; håll dock inversa specar här.)

```sql
CREATE TABLE IF NOT EXISTS actions (
    id          TEXT PRIMARY KEY,        -- uuid4 hex
    memaix_user TEXT NOT NULL,
    project     TEXT NOT NULL,
    tool        TEXT NOT NULL,
    summary     TEXT NOT NULL,           -- människoläsbar ("Skapade händelse 'Möte'")
    reversible  INTEGER NOT NULL,        -- 1 = kan ångras
    inverse     TEXT,                    -- JSON {tool, args} eller NULL om irreversibel
    status      TEXT NOT NULL DEFAULT 'done',  -- done|undone|undo_failed
    created_at  TEXT NOT NULL,
    undone_at   TEXT,
    undo_of     TEXT,                    -- action_id om denna post är en ångring
    undo_action_id TEXT                  -- id på ångringen som återställde denna
);
CREATE INDEX IF NOT EXISTS idx_actions_scope ON actions(project, created_at);
```

---

## 5. Registrering (recording)

`timeline/record.py` — `record_action(store, user, project, tool, summary,
inverse: dict | None)`; `inverse=None` ⇒ `reversible=0`.

Var registreras det? Efter lyckad skrivning, i tool-lagret (som index-hooken i
#2). Två vägar:
- **Direkt i verktygen** (mest exakt): t.ex. `calendar_create` returnerar event-id
  → registrera `inverse={"tool":"calendar_delete","args":{"project","id"}}`.
- **Via en central hook** i `server._tool_call` (funktion #5-refaktorn) för verktyg
  vars invers kan härledas ur argument+resultat — en `INVERSE_BUILDERS`-map
  `tool → fn(args, result) -> inverse|None`. Verktyg utan builder loggas som
  `reversible=0` (visas men utan ångra-knapp).

Rekommendation: central hook i `_tool_call` + en `INVERSE_BUILDERS`-tabell, så
registreringen ligger på ett ställe och nya verktyg är opt-in reversibla.

> Not: hooken måste ha *resultatet* (t.ex. nytt event-id) — `_tool_call` har det
> redan (`_audited` returnerar det). Bygg invers *efter* lyckat anrop.

---

## 6. Ångra (undo)

`timeline/undo.py` — `undo(store, acl, user, action_id) -> dict`:
1. Hämta action; kräv `status=='done'` och `reversible==1` (annars konflikt/fel).
2. ACL: `acl.enforce(user, action.project, need_for(action.tool))` — samma roll
   som originalet.
3. **Claim** `status: done → undone` (compare-and-set; hindrar dubbel-ångra).
4. Kör `inverse` via dispatch (samma som utkorgens `execute`): `fn(acl, user,
   project, **inverse.args, _confirmed=True)`. Vid fel → `status='undo_failed'`,
   returnera felet.
5. Registrera själva ångringen som en action med `undo_of=action_id`; sätt
   `undo_action_id` på originalet. Audit-logga.

Optimistisk låsning på backlog/minne kan ge konflikt om något ändrats sedan dess
— returnera det tydligt ("kan inte ångra: posten har ändrats sedan").

---

## 7. MCP-yta och board

Verktyg i `server.py` (via `_tool_call`):

| Verktyg | Signatur | Roll |
|---------|----------|------|
| `timeline_list` | `(project: str\|None=None, limit: int=50)` | reader (synliga projekt) |
| `timeline_undo` | `(action_id: str)` | roll som originalåtgärden krävde |

**Board:** en "Historik/Tidslinje"-vy (`GET /board/api/timeline?project=…`) med
en rad per åtgärd, ångra-knapp där `reversible && status=='done'`, och tydlig
märkning av `undone`/`irreversible`. `POST /board/api/timeline/{id}/undo`
enforce:ar rätt roll.

Koppling till #1: en notis kan inkludera "ångra"-länk till senaste åtgärd.

---

## 8. Säkerhet & integritet

- **Ångra kräver samma behörighet** som originalåtgärden och samma projekt-ACL —
  en reader kan inte ångra en owners statusändring.
- **Idempotent:** compare-and-set på `done → undone` gör att dubbelklick/retry
  ångrar en gång.
- **Inversen körs med `_confirmed=True`** internt (den är redan användarinitierad
  och behörighetskollad) — men bara via `undo`, aldrig från klient-input.
- **Irreversibelt är irreversibelt:** hitta aldrig på en falsk ångra för
  `email_send`; visa förklaring och peka på utkorgen (#3).
- **Inga hemligheter i `summary`/`inverse`** utöver referenser (ids, sökvägar);
  logga inte innehåll. Audit för varje ångring.
- **Retention:** rensa gamla `actions` efter konfigurerbar tid (default 90 dagar);
  ångra-möjligheten är främst för nyliga misstag.

---

## Byggordning

1. **ActionsStore** (`timeline/store.py`) — SQLite + statusmaskin. *Isolerat.*
2. **Inverse-builders** (`timeline/inverse.py`) — `INVERSE_BUILDERS` per tool.
3. **Recording-hook** — registrera i `_tool_call` efter lyckat anrop.
4. **Undo** (`timeline/undo.py`) — claim + dispatch invers + logga ångring.
5. **MCP-yta** (`server.py`) — timeline_list / timeline_undo.
6. **Board** — tidslinjevy + undo-route.
7. **Config + docs.**
8. **CI** — grönt.

---

## Utvecklingsinstruktioner

Konventioner: se funktion #1-doket. Kör `python -m pytest -q` från `gateway/`.
Förutsätter funktion #5-refaktorn (`_tool_call`) som redan finns i `server.py`.

### Steg 1 — `timeline/store.py`
Paket `timeline/__init__.py` + `ActionsStore`:
```python
class ActionsStore:
    def for_path(cls, db_path) -> "ActionsStore"
    def record(self, user, project, tool, summary, inverse: dict|None) -> str  # id
    def get(self, action_id) -> dict | None
    def list(self, projects: list[str], limit: int) -> list[dict]  # nyast först
    def claim_undo(self, action_id) -> bool   # done → undone (compare-and-set)
    def mark_undo_failed(self, action_id) -> None
    def link_undo(self, original_id, undo_action_id) -> None
    def purge_older_than(self, cutoff_iso) -> int
```
**Test** (`tests/test_timeline_store.py`): record+get+list (ordning); `claim_undo`
True första, False andra; irreversibel post (`inverse=None`) → `reversible=0`.

### Steg 2 — `timeline/inverse.py`
`INVERSE_BUILDERS: dict[str, Callable[[args, result], dict|None]]` för
`calendar_create` (→ `calendar_delete`), `calendar_update` (fält före → tillbaka;
kräver att verktyget returnerar/åtkomst till gamla fält — annars registrera
reversibel först när det stöds), `backlog_set_status`/`score`/`comment` (→ skriv
tillbaka via expected_version), `backlog_add` (→ set rejected), `board_move`
(→ gammal status), `email_create_draft` (→ radera utkast), `memory_write`/`append`
(→ `memory_revert(commit)` från resultatets commit), `pm_plan_sprint`
(→ ta bort sprint). `build_summary(tool, args, result) -> str`. Verktyg utan
builder → `(summary, None)`. **Test** (`tests/test_timeline_inverse.py`): varje
builder producerar rätt `{tool, args}`; okänt verktyg → None.

### Steg 3 — Recording-hook i `_tool_call`
Efter lyckat `_audited`-anrop: om `tool in INVERSE_BUILDERS` (eller alltid, med
`reversible=0` som default), bygg summary + inverse och `record`. Slå in i
try/except (får ej fälla verktyget). Gör hooken avstängbar (hoppa om
`MEMAIX_ACTIONS_DB` ej satt) så befintliga tester inte tvingas registrera.
**Test:** `calendar_create` via server → en `timeline_list`-post med reversibel
invers; `email_send` → post med `reversible=0` och förklaring.

### Steg 4 — `timeline/undo.py`
`undo(store, acl, user, action_id, *, tools=None)` enligt §6. Dispatch:a inversen
med `_confirmed=True`. Registrera ångrings-action med `undo_of`. **Test**
(`tests/test_timeline_undo.py`): undo av `calendar_create` anropar
`calendar_delete` med rätt id; dubbel-undo → konflikt; undo av irreversibel →
fel; ACL: fel roll nekas; undo loggas som egen action med `undo_of`.

### Steg 5 — MCP-yta i `server.py`
Lat `_get_actions()`. `timeline_list` (ACL-filtrera synliga projekt),
`timeline_undo` (enforce originalets roll). **Test** (`tests/test_server.py`):
skapa → lista → ångra → posten `undone`, effekten inverterad (fejk-tool).

### Steg 6 — Board
`GET /board/api/timeline` + `POST /board/api/timeline/{id}/undo` (enforce owner
för mutation). Tidslinjevy i `board.html` med ångra-knapp/irreversibel-märkning.

### Steg 7 — Config + docs
`memaix.example.yaml`: `timeline.retention_days`. Registrera doket i INDEX
(gjort); uppdatera `DEVELOPMENT-PROPOSALS.md`.

### Steg 8 — Kör allt
`cd gateway && python -m pytest -q` + `python3 scripts/check-docs-index.py`.

### Acceptanskriterier
- [ ] Skrivande åtgärder via connectorn dyker upp i `timeline_list` nyast först, med människoläsbar summary.
- [ ] `timeline_undo` av `calendar_create` tar bort händelsen; av `memory_write` återställer förra versionen; av `board_move` sätter tillbaka gammal status.
- [ ] `email_send` visas som `irreversible` utan ångra-knapp och med förklaring.
- [ ] Ångra är idempotent (dubbelklick ångrar en gång) och kräver originalets roll.
- [ ] Ångra registreras som egen post med `undo_of`; original får `undone`-status.
- [ ] Optimistisk konflikt (posten ändrad sedan) rapporteras tydligt istället för att skriva över.
- [ ] Recording-hooken är avstängbar och fäller aldrig själva verktyget; hela sviten + docs-index grön.

---

## Framtida arbete
- "Ångra allt från den här sessionen"/tidsintervall (batch-undo i omvänd ordning).
- Redo (ångra en ångring).
- Snapshot-baserad ångra för filer utan git (temp-kopia före skrivning).
- Visa tidslinjen filtrerad per källa/verktyg och sök i den (koppla till #2).
- "Mjuk återkallning" av mejl där providern stödjer det (Gmail undo-send-fönster).
