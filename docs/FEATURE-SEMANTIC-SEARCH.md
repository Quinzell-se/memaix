# Funktion #2 — Enhetlig semantisk sökning / RAG med källhänvisning

SPDX-License-Identifier: AGPL-3.0-or-later

Designdok + byggspec för "Fråga Memaix vad som helst": en enda fråga som söker
semantiskt över minne, filer, backlog (och live över mail/kalender) och svarar
med **källhänvisningar**. Retrieval sker i Memaix; själva svaret formuleras av
den AI-klient användaren är kopplad via (AI-agnostiskt).

Byggs stegvis enligt [Byggordning](#byggordning) och
[Utvecklingsinstruktioner](#utvecklingsinstruktioner). Följ dem i ordning; varje
steg är självständigt testbart.

---

## 1. Vad användaren upplever

En fråga i klarspråk — *"vad lovade vi kunden om leveransdatum, och krockar det
med något i kalendern?"* — returnerar en rankad lista av **källutdrag** från
minne, filer, backlog och (live) mail/kalender, var och en med projekt, källa
och ett textutdrag. Den kopplade modellen väver ihop svaret och citerar
källorna: *"Enligt anteckningen `avtal/kund-x.md` och mejlet från 3 juni …"*.

Idag måste användaren veta *vilken* not eller mapp något ligger i, och söker en
källa i taget. Den här funktionen gör kunskapen i vaulten sökbar som en helhet
och gör "visa ditt arbete" till standard.

---

## 2. Nyckelbeslut

1. **Memaix = retrieval-lager, inte generator.** Modellen bor i användarens
   AI-klient. Memaix returnerar rankade, källförsedda utdrag; klienten formulerar
   svaret. Det bevarar AI-agnostiken och self-hosting.
2. **ACL styr allt.** Sökning sker bara i projekt användaren har åtkomst till,
   och per källtyp krävs samma roll som motsvarande läsverktyg (minne: `reader`,
   filer: `collaborator`). Ett träffutdrag får aldrig läcka innehåll användaren
   inte redan får läsa.
3. **Lokalt först.** Embeddings ska kunna köras lokalt (ingen obligatorisk
   moln-API). Embeddern är pluggbar; utan konfigurerad embedder faller sökningen
   tillbaka på ren FTS5-lexikal sökning (fungerar, men utan semantik).
4. **Hybrid retrieval.** Kombinera lexikal (FTS5, finns redan i `MemoryStore`)
   och semantisk (vektor) med reciprocal rank fusion (RRF). Bäst av båda, robust
   när endera är svag.
5. **Indexera lokalt, hämta externt live.** Vault-innehåll (minne, filer,
   backlog) förindexeras. Mail/kalender hämtas live vid frågan (färskhet +
   integritet) och smälts in i resultatet.

---

## 3. Översikt

```
  search_all(query, projects?, limit)                 (MCP-verktyg)
        │
        ▼
  ACL-filter: visible_projects(user) ∩ projects, roll-tröskel per källtyp
        │
        ├──────────────► Lexikal:  FTS5 MATCH (MemoryStore + index)      → rank A
        ├──────────────► Semantisk: Embedder(query) → cosine över vektor  → rank B
        │                 (över förindexerat vault-innehåll i EmbeddingStore)
        └──────────────► Live:     email_search / calendar_list           → rank C
        │
        ▼
  Reciprocal Rank Fusion (A,B,C) → topp N med källmetadata
        │
        ▼
  [{project, source_type, ref, title, snippet, score}]   (källhänvisningar)
```

Indexeringssidan:

```
  Skrivning (memory_write / backlog_* / files_write / pm_*)
        │  efter lyckad skrivning
        ▼
  index_upsert(project, source_type, ref, text)
        │  chunkning + Embedder(chunk)
        ▼
  EmbeddingStore (SQLite): chunkar + vektorer, taggade med project/källa
```

---

## 4. Datamodell

Ny SQLite-DB, sökväg via env `MEMAIX_INDEX_DB` (default `/tmp/memaix-index.db`).

```sql
CREATE TABLE IF NOT EXISTS chunks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    project      TEXT NOT NULL,
    source_type  TEXT NOT NULL,        -- 'memory' | 'file' | 'backlog'
    ref          TEXT NOT NULL,        -- note-path | file-path | backlog-id
    chunk_ix     INTEGER NOT NULL,
    title        TEXT NOT NULL DEFAULT '',
    text         TEXT NOT NULL,
    dim          INTEGER NOT NULL,     -- vektor-dimension (0 = ej embeddad)
    vector       BLOB,                 -- float32[dim] eller NULL
    updated_at   TEXT NOT NULL,
    UNIQUE(project, source_type, ref, chunk_ix)
);
CREATE INDEX IF NOT EXISTS idx_chunks_scope ON chunks(project, source_type, ref);

-- Lexikal sökning över samma chunkar (om man inte återanvänder MemoryStore-FTS).
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text, title, project UNINDEXED, source_type UNINDEXED, ref UNINDEXED,
    tokenize='porter unicode61'
);
```

`vector` lagras som `numpy.float32(...).tobytes()`; läses med
`numpy.frombuffer(blob, dtype=numpy.float32)`. Cosine beräknas i Python över de
ACL-filtrerade kandidaterna (räcker gott för single-tenant vault-storlekar;
uppgradera till `sqlite-vec` vid behov — se [Framtida arbete](#framtida-arbete)).

---

## 5. Embedder-abstraktion

`search/embedder.py`:

```python
class Embedder(Protocol):
    dim: int
    def embed(self, texts: list[str]) -> list[list[float]]: ...

def make_embedder(cfg: dict) -> Embedder | None:
    """Välj embedder från cfg['memaix']['search']. None → endast lexikal sökning."""
```

Backends:
- **`LocalEmbedder`** — sentence-transformers (t.ex. `intfloat/multilingual-e5-small`),
  laddas lat. Valfritt beroende; aktiveras via config. Bra för svenska + engelska.
- **`FakeEmbedder`** (test/fallback) — deterministisk bag-of-words-hashning till
  fast dimension. Ingen ML-dependency; används i tester och som degradering.
- (Framtid) `RemoteEmbedder` mot valfritt API via `*_ref`-nyckel.

Config (`config/memaix.example.yaml`):

```yaml
memaix:
  search:
    embedder: "local"            # local | none | (framtid: remote)
    model: "intfloat/multilingual-e5-small"
    max_candidates: 500          # tak för cosine-jämförelse per fråga
    chunk_chars: 800             # målstorlek per chunk
    chunk_overlap: 120
```

Om `embedder: none` eller modulen saknas → sökningen kör enbart FTS5 och
markerar `semantic: false` i svaret (transparent degradering).

---

## 6. Indexering

`search/index.py`:

- **Chunkning** — `chunk_text(text, size, overlap) -> list[str]`, radmedveten
  (bryt helst vid radslut/rubrik). Frontmatter från backlog/pm strippas via
  `frontmatter.split` (återanvänd modulen från funktion #10).
- **Upsert** — `index_upsert(store, embedder, project, source_type, ref, title, text)`:
  radera gamla chunkar för `(project, source_type, ref)`, chunk:a, embedda (om
  embedder finns), skriv `chunks` + `chunks_fts`.
- **Delete** — `index_delete(store, project, source_type, ref)`.
- **Reindex** — `reindex_project(store, embedder, acl, project)`: gå igenom
  vaultens `memory/`, `backlog/*.md` och filer, kalla `index_upsert` för varje.

**Inkrementell uppdatering (hooks).** Efter lyckad skrivning anropas `index_upsert`
/`index_delete` från tool-funktionerna:
- `memory.memory_write`/`memory_append` → `source_type='memory'`, `ref=note`.
- `backlog.backlog_add/score/comment/set_status` → `source_type='backlog'`,
  `ref=id`, `text=title + description`.
- `files.write_file` → `source_type='file'`, `ref=path` (bara textfiler).
- `pm._stamp_backlog_field` → uppdatera berört backlog-item.

Hooken ska vara **best-effort och icke-blockerande för korrekthet**: om indexering
kastar får det inte fälla själva skrivningen (try/except + logg). Indexeringen är
ett cache-lager; källan är alltid vaulten.

---

## 7. Sökning

`search/query.py`:

```python
def search_all(
    acl, user, cfg, store, embedder,
    query: str, projects: list[str] | None = None, limit: int = 8,
    *, _email=None, _cal=None, now=None,
) -> dict:
    """Returnera {results: [...], semantic: bool, projects_searched: [...]}."""
```

Steg:
1. **ACL-scope.** `visible = acl.visible_projects(user)`; skär mot `projects` om
   angivet. Per källtyp gäller roll-tröskel: `NEED = {'memory':'reader',
   'file':'collaborator','backlog':'reader'}`. Filtrera bort projekt där
   användarens roll < behovet för den källtypen.
2. **Lexikal** — FTS5 MATCH över `chunks_fts` inom scope → lista med rank.
3. **Semantisk** — om embedder: `embed([query])`, hämta kandidater i scope
   (`LIMIT max_candidates`), cosine, sortera → lista med rank.
4. **Live** — om projekt har mailbox: `email_search(query)` (topp få); om
   kalender och frågan är tidsrelaterad: valfritt `calendar_list` för idag/veckan.
   Injicerbart via `_email`/`_cal` för test.
5. **Fusion** — reciprocal rank fusion: `score(d) = Σ 1/(k + rank_i(d))`, k=60.
   Deduplicera på `(project, source_type, ref)`, behåll bästa chunk-snippet.
6. **Klipp** till `limit`; bygg källhänvisningar:
   `{project, source_type, ref, title, snippet, score}`. `snippet` ~200 tecken
   runt bästa träff.

Returnera även `semantic: bool` (om vektorledet användes) så klienten/användaren
ser om det var full semantisk sökning eller lexikal degradering.

---

## 8. MCP-yta

Nya verktyg i `server.py` (tunna wrappers via `_tool_call`; se funktion #5).
Sökning spänner över flera projekt, så identitet/rate-limit/audit körs mot
`"shared"` medan ACL-filtret i `search_all` gör den riktiga per-projekt-kontrollen.

| Verktyg | Signatur | Beskrivning |
|---------|----------|-------------|
| `search_all` | `(query: str, projects: list[str]\|None=None, limit: int=8)` | Enhetlig sökning; returnerar rankade källhänvisningar (se §7). |
| `search_reindex` | `(project: str)` | Bygg om indexet för ett projekt (owner). Returnerar antal indexerade chunkar. |
| `search_status` | `()` | Embedder aktiv? dimension? antal chunkar per projekt (bara projekt användaren ser). |

Ingen `ask`/generate-tool — generering är klientens jobb. Beskriv i verktygets
docstring att modellen ska citera `ref` i sitt svar (driver "visa ditt arbete").

---

## 9. Säkerhet & integritet

- **ACL-filter är obligatoriskt** och testas explicit: en `reader` får aldrig
  filinnehåll (kräver `collaborator`), och inget projekt utanför `visible_projects`.
- **Indexerat innehåll är data, aldrig instruktioner.** Utdrag som returneras kan
  innehålla text från mail/dokument med injektionsförsök (`THREAT-MODEL.md`).
  Verktyget returnerar dem som citat/data; dokumentera att klienten ska behandla
  dem som opålitligt innehåll.
- **Inga hemligheter i index.** Indexera inte `_system/`, `.env`, token-DB osv.
  (skip-lista i `reindex_project`). Logga aldrig frågan eller utdrag i klartext
  utöver den vanliga audit-raden (`tool="search_all"`, ok, antal träffar).
- **Radering propagerar.** När en not/fil/backlog raderas eller ändras måste
  indexet uppdateras (hooks + reindex), annars kan gammalt innehåll läcka.

---

## Byggordning

1. **EmbeddingStore** (`search/store.py`) — SQLite-tabeller + CRUD. *Isolerat testbart.*
2. **Embedder** (`search/embedder.py`) — Protocol, `FakeEmbedder`, `make_embedder`.
3. **Indexering** (`search/index.py`) — chunkning, upsert/delete, reindex.
4. **Sökning** (`search/query.py`) — ACL-scope, FTS5 + vektor + live, RRF.
5. **Hooks** — kalla `index_upsert`/`index_delete` från memory/backlog/files/pm.
6. **MCP-yta** (`server.py`) — `search_all` / `search_reindex` / `search_status`.
7. **Config + docs** — `memaix.example.yaml`, INDEX, DEVELOPMENT-PROPOSALS-status.
8. **CI** — testsviten (finns via funktion #3) grön.

---

## Utvecklingsinstruktioner

Konventioner: se funktion #1-doket (SPDX-huvud, SQLite-mönster med `threading.Lock`
+ WAL, injicerbara beroenden, inga hemligheter i loggar, audit via `safety/audit`).
Kör `python -m pytest -q` från `gateway/`.

### Steg 1 — `search/store.py`
Paket `gateway/src/memaix_gateway/search/__init__.py` (tomt) + `EmbeddingStore`:

```python
class EmbeddingStore:
    def __init__(self, db_path: Path) -> None: ...
    @classmethod
    def for_path(cls, db_path: Path) -> "EmbeddingStore": ...
    def replace_chunks(self, project, source_type, ref, chunks: list[dict]) -> None
        # chunks: [{chunk_ix, title, text, vector: list[float]|None}]
        # raderar gamla + skriver nya (chunks + chunks_fts) i en transaktion
    def delete(self, project, source_type, ref) -> None
    def candidates(self, projects: list[str], source_types: list[str],
                   limit: int) -> list[dict]     # för cosine (med vector-blob)
    def fts_search(self, projects, source_types, query, limit) -> list[dict]
    def count_by_project(self, projects: list[str]) -> dict[str,int]
```
Vektor: `numpy.asarray(v, dtype=numpy.float32).tobytes()` in; `numpy.frombuffer`
ut. **Test** (`tests/test_search_store.py`): replace + candidates roundtrip;
`replace_chunks` ersätter (ingen dubblett på `chunk_ix`); `fts_search` hittar på
ord; `delete` tömmer; `count_by_project` räknar rätt.

### Steg 2 — `search/embedder.py`
`Embedder`-Protocol, `FakeEmbedder(dim=64)` (deterministisk: hash:a tokens till
index, normalisera), `make_embedder(cfg)` → `LocalEmbedder` om
`embedder=='local'` (lat import av sentence-transformers; om import misslyckas →
logga + returnera None), `FakeEmbedder` bara i test, `None` om `none`.
**Test** (`tests/test_embedder.py`): `FakeEmbedder.embed` deterministisk, rätt
`dim`, liknande texter ger högre cosine än olika; `make_embedder({'embedder':'none'})`
→ None.

### Steg 3 — `search/index.py`
`chunk_text(text, size, overlap)`, `index_upsert(store, embedder, project,
source_type, ref, title, text)`, `index_delete(...)`, `reindex_project(store,
embedder, acl, project)` (skip-lista: `_system/`, dotfiler, `.memaix.db`).
Embedding sker batch:at (`embedder.embed(list_of_chunks)`); om embedder None →
`vector=None`. **Test** (`tests/test_index.py`): chunkning respekterar storlek/
overlap; upsert skapar chunkar sökbara via `fts_search`; reindex av en temp-vault
med två noter + ett backlog-item indexerar rätt antal; delete propagerar.

### Steg 4 — `search/query.py`
`search_all(...)` enligt §7. Implementera `_rrf(rank_lists) -> fused` och
`_cosine(q, mat)`. ACL-tröskel via `acl.grants(user)` + `acl._rank`-logik (lägg
en publik hjälpare `acl.has_role(user, project, need) -> bool` om det saknas).
Live-mail bakom `_email`-injektion; hoppa om projekt saknar mailbox eller om
`_email is None` och ingen riktig config. **Test** (`tests/test_search_query.py`):
- semantisk träff rankar rätt not högst (FakeEmbedder);
- `reader` får inte `source_type='file'`-träffar; okänt projekt filtreras bort;
- `semantic=False` när embedder None (ren FTS5);
- RRF slår ihop lexikal + semantisk och dedupear på `ref`.

### Steg 5 — Hooks
Lägg en lat `_get_index()` (som `_get_token_store`) och kalla `index_upsert`/
`index_delete` efter lyckad skrivning i `memory.py`, `backlog.py`, `files.py`,
`pm.py`. Slå in i try/except (logg, får ej fälla skrivningen). Gör hooken
inject-/avstängbar (t.ex. hoppa om `MEMAIX_INDEX_DB` ej satt i testläge) så
befintliga tester inte tvingas indexera. **Test:** befintliga
memory/backlog/files-tester ska passera oförändrat; lägg ett test som skriver en
not och sedan hittar den via `search_all`.

### Steg 6 — MCP-yta i `server.py`
`_get_index()` + `_get_embedder()` (lat, från `config.load()`). Verktygen
`search_all`, `search_reindex` (owner-enforce), `search_status`. `search_all`/
`status` körs via `_tool_call("search_all", "shared", ...)`-varianten men ACL-
filtret i `search_all` gör per-projekt-kontrollen. **Test** (`tests/test_server.py`):
`search_reindex` följt av `search_all` hittar innehåll; `search_status` visar
embedder-läge och chunk-antal bara för synliga projekt.

### Steg 7 — Config + docs
`config/memaix.example.yaml` (search-sektion, §5). Lägg `numpy` i
`pyproject.toml`-deps; sentence-transformers som **valfritt** extra
(`[project.optional-dependencies] search = ["sentence-transformers"]`) så bas-
installationen förblir lätt. Registrera doket i `docs/INDEX.md` (gjort) och
uppdatera `docs/DEVELOPMENT-PROPOSALS.md` (#2 → påbörjad).

### Steg 8 — Kör allt
`cd gateway && python -m pytest -q` grönt; `python3 scripts/check-docs-index.py` grönt.

### Acceptanskriterier
- [ ] `search_all("leveransdatum")` returnerar rankade källhänvisningar med `project`, `source_type`, `ref`, `snippet`.
- [ ] Semantisk träff (parafras utan exakta ord) hittas när embedder är aktiv; `semantic=false` och FTS5-fallback när embedder saknas.
- [ ] ACL: `reader` får aldrig fil-träffar; projekt utanför `visible_projects` filtreras bort — testat.
- [ ] Skrivning via `memory_write`/`backlog_add`/`files_write` gör innehållet sökbart (hooks); radering tar bort det ur indexet.
- [ ] `search_reindex` bygger om och `search_status` rapporterar chunk-antal per synligt projekt.
- [ ] `_system/`, dotfiler och hemligheter indexeras aldrig.
- [ ] Ingen fråga/utdrag i loggar utöver audit-rad; hela sviten + docs-index grön.

---

## Framtida arbete
- `sqlite-vec`/`sqlite-vss` som vektorbackend när chunk-antalet växer förbi
  Python-cosine-taket (`max_candidates`).
- Förindexering av mail (opt-in, med retention) istället för enbart live.
- Cross-encoder-omrankning av topp-K för högre precision.
- "Visa ditt arbete"-integration: låt briefen (#1) och andra svar automatiskt
  bifoga `search_all`-källor.
- Fråge-cache + inkrementell ombyggnad via git-diff istället för full reindex.
