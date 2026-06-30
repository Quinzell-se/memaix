# Minnes-retrieval — semantiskt lager över vaulten (lager 2)

Hur vi ger Memaix **persistent, sökbart minne** utan att byta ut sanningskällan eller öppna en ny
injektionsyta. Bakgrund/beslut: backlog **MEX-008** (Letta utvärderat och valts bort som *grund* —
se kommentaren där) + `THREAT-MODEL.md`. Detta är **lager 2** i den lagrade minnesmodellen:

1. Aktivt tillstånd → SQLite (`MemoryStore`, finns)
2. **Återkallningsindex → embeddings över vaulten (detta dokument)**
3. Kanonisk kunskap → git-versionerad vault (finns; sanningskälla + audit)
4. Grindad konsolidering → separat, schemalagt steg (lager 3, senare)

## Princip
Indexet är **härledd, läs-bar data** ovanpå git-vaulten. Det **indexerar bara redan existerande
kanon** (innehåll som kommit in via den grindade skrivvägen) → det ing-esterar ingen ny otrodd data
och skapar **ingen ny skrivväg**. Därmed: **noll ny injektionsyta**. (Till skillnad från Letta, där
poängen *är* en autonom skrivväg från otrodd indata.)

## Var det slottar in (befintlig kod)
`backends/memory_store.py` = per-vault SQLite med `notes` + `notes_fts` (FTS5) + git. `write`/`append`
river och bygger om `notes_fts` per skrivning. Lager 2 lägger ett vektorindex **i samma DB** och hakar
in i **samma skrivhook**. Eftersom `_get_store` redan är per projekt och ACL-enforced bor vektorerna i
vaultens egen DB → **RBAC-isolering gratis** (ett projekts vektorer kan inte nå ett annat).

## Komponentval
- **Vektorstore: `sqlite-vec`** (in-process C-extension). Virtuell tabell `notes_vec` i samma fil.
  Ingen ny server/Postgres. Brute-force KNN räcker upp till ~10k–100k chunks/vault. *Alt om ni växer
  ur det:* LanceDB (också embedded).
- **Embedding-modell: `bge-m3`** via Ollama på alienqronk (~1024-dim, ~2 GB VRAM, samexisterar med
  Gemma). Flerspråkig → hanterar **svenska + engelska** (därför inte nomic-embed, som är engelsk-
  centrerad). *Att validera:* liten retrieval-eval BGE-M3 vs Qwen3-Embedding-0.6B/4B på er egen vault
  innan låsning. Modell-id + dim lagras med indexet → modellbyte = reindex.

## Schema (tillägg, minimalt)
- `chunks(path, chunk_index, text)`
- `notes_vec` (sqlite-vec: `embedding float[1024]`, rowid → `chunks.rowid`)
- Versionsrad: `embed_meta(model, dim, built_at)`.

## Chunking
Markdown → chunka per rubrik/stycke (~256–512 tokens, lite overlap). En vektor per chunk. Retrieval
returnerar chunks → mappas till `path` + snippet. Detta *är* "dumpa aldrig" (`SAFETY.md §6`): modellen
får relevanta bitar, inte hela noteringar.

## Skrivhook (återanvänd befintlig)
I `write`/`append`, där `notes_fts` rivs/återbyggs: chunka → embedda varje chunk → `DELETE` gamla
chunks för `path` → `INSERT` nya → upsert `notes_vec`. Samma transaktion, samma git-commit. Falla
tyst tillbaka (logga) om embed-tjänsten är nere — skrivningen får aldrig blockeras av indexering.

## `memory_search` → hybrid (bakåtkompatibelt)
- Lägen: `keyword` (dagens FTS5), `semantic` (vektor-KNN), **`hybrid` (default)**.
- Hybrid: kör FTS5 **och** vektor-KNN, slå ihop med **Reciprocal Rank Fusion (RRF)**. Robustare än ren
  vektor — exakta termer/ID:n (t.ex. "MEX-008") fångas av FTS, semantiskt nära av vektorn.
- Retur förblir `[{path, snippet}]` + valfri `score`. Inga andra verktyg ändras. `reader`-roll,
  ACL-enforced (oförändrat).

## Drift
- **`reindex()`**: `list_all()` → chunk → embed → fyll `notes_vec`. Körs vid uppgradering + modellbyte.
- **Graceful degradation**: embed-tjänst nere → `memory_search` faller tillbaka till FTS5, bryts aldrig.
- **Doctor-check**: embed-endpoint nåbar + index-färskhet (antal chunks vs antal noteringar).

## Säkerhet (sammanfattning)
- Ingen ny otrodd-data-ingestion, ingen ny skrivväg → ingen ny injektionsyta.
- Per-vault DB → RBAC-isolering per (projekt) gratis; sök korsar aldrig projektgräns.
- Härledd/ombyggbar; git-vaulten förblir sanning + audit.

## Byggordning (minsta första PR)
1. `sqlite-vec` + `notes_vec`/`chunks`/`embed_meta`-schema + Ollama-embed-klient (`bge-m3`).
2. Haka in i `write`/`append` + `reindex()` för befintligt innehåll.
3. `memory_search` hybrid (RRF), bakåtkompatibel retur.
4. Doctor-check + FTS-fallback.
5. Retrieval-eval på svensk vault (BGE-M3 vs Qwen3) → lås modell.

## Acceptanskriterier
- [ ] `memory_search` returnerar semantiskt relevanta träffar som FTS5 missar; ID:n/exakta termer fångas fortf.
- [ ] Indexet byggs/uppdateras i samma transaktion som skrivningen; reindex återskapar identiskt.
- [ ] Embed-tjänst nere → sökning degraderar till FTS5 utan fel.
- [ ] Vektorer isolerade per vault; sök korsar aldrig projekt/RBAC.
- [ ] Modell-id + dim versionerade; modellbyte triggar reindex.
- [ ] Retur bakåtkompatibel; inga andra verktyg påverkade.
