# Funktion #8 — Nextcloud som förstklassig backend

SPDX-License-Identifier: AGPL-3.0-or-later

Designdok + byggspec för att lyfta Nextcloud från "valfri CalDAV/WebDAV" till en
**förstklassig ryggrad** för self-host: filer, kontakter, uppgifter, chatt, Deck
och dokument. Bygger på connector-ramverket
([FEATURE-CONNECTOR-FRAMEWORK.md](FEATURE-CONNECTOR-FRAMEWORK.md)) och
topologin i [SELF-HOST-STACK.md](SELF-HOST-STACK.md) / [BACKENDS.md](BACKENDS.md).

Byggs stegvis enligt [Byggordning](#byggordning) och
[Utvecklingsinstruktioner](#utvecklingsinstruktioner). Fas 4 i [ROADMAP.md](ROADMAP.md).

---

## 1. Varför

Nextcloud ligger redan i `docker-compose.yml` (profil) och används för CalDAV/WebDAV.
För en kund som vill **maximalt dataägande** är Nextcloud den självklara platsen för
filer, kontakter och chatt — utan tredjepart. Att göra den förstklassig särskiljer
Memaix på self-host-marknaden och ger "min assistent når mina Nextcloud-grejer" via
per-user-koppling.

## 2. Nyckelbeslut

1. **Allt går via connector-ramverket.** Varje Nextcloud-förmåga är en adapter bakom
   ett kapabilitets-protokoll (`FilesBackend`, `ContactsBackend`, `ChatBackend`, …).
   Inga nya specialvägar i verktygen.
2. **Öppna protokoll först.** WebDAV (filer), CardDAV (kontakter), CalDAV VTODO
   (uppgifter) — standardiserat och testbart. Nextcloud-specifika API:er (Talk, Deck,
   Notes) via deras OCS/REST-API:er.
3. **Per-user via app-lösenord eller OAuth.** Nextcloud stödjer app-specifika lösenord
   och OAuth2; per-user-koppling återanvänder token-store + `account_link`-flödet.
4. **Läs in i minnet/sök.** Nextcloud-filer och Notes indexeras i semantisk sökning
   (#2) så "fråga vad som helst" täcker dem. Kontakter matar kontaktupplösning.
5. **Sammanlänka, inte ersätt.** Deck ↔ backlog och Notes ↔ memory är *synk*, inte
   migrering — användaren kan jobba i Nextclouds egna UI.

## 3. Kapabiliteter & adaptrar

| Nextcloud | Protokoll/API | Kapabilitet (connector) | Nya MCP-verktyg |
|-----------|---------------|-------------------------|-----------------|
| Files | WebDAV | `FilesBackend` | (befintliga `files_*`) |
| Contacts | CardDAV | `ContactsBackend` | `contacts_search`, `contacts_get` |
| Tasks | CalDAV VTODO | `TasksBackend` | `tasks_list/add/complete` |
| Talk | OCS Talk API | `ChatBackend` | `chat_post`, `chat_read` (notiskanal #1) |
| Deck | Deck REST | `IssueBackend`-lik | `deck_sync` (↔ backlog) |
| Notes | Notes REST | (sync) | `notes_sync` (↔ memory) |
| Collabora/OnlyOffice | WOPI | (dokumentgen) | via `files_write` av .odt/.docx |

Prioritet: **Files → Contacts → Talk** (störst nytta), sedan Tasks/Notes/Deck,
sist dokumentgenerering.

## 4. Files (WebDAV) som förstklassig backend

En `webdav` `FilesBackend` i connector-ramverket:
- `list(path)`, `read(path)`, `write(path, content)`, `search(query, path)` mot
  `https://<nc>/remote.php/dav/files/<user>/…`.
- Auth: app-lösenord (`*_ref`) för delad resurs, eller per-user token.
- **Sökbarhet:** en indexeringshook (#2) som vid `files_write`/reindex drar in
  Nextcloud-filer i vektorindexet (respektera skip-lista/storlekstak).
- Path-säkerhet: samma `paths.py`-validering som lokal vault (ingen traversal).

## 5. Contacts (CardDAV) → kontaktupplösning

En `ContactsBackend` som söker CardDAV-adressböcker:
- `contacts_search(query)` → `[{name, email, phone, org}]`; `contacts_get(id)`.
- **Integrationsvärde:** mail (#) och kalender kan slå upp "vem är avsändaren", och
  briefen (#1) kan visa namn istället för råa adresser. Regler (#4) kan matcha på
  "kontakt tillhör kund X".

## 6. Talk som chattkanal

En `ChatBackend` mot Nextcloud Talk (OCS):
- `chat_post(room, text)`, `chat_read(room, since)`.
- **Dubbelnytta:** registreras som **notiskanal i briefen (#1)** (`{"type":"nextcloud_talk",
  "room": "..."}`) — en helt self-hostad push-väg, och som ingång för snabbfångst
  (Talk-meddelande → regel #4 → backlog).

## 7. Deck ↔ backlog och Notes ↔ memory (synk)

- **Deck-synk:** mappa Deck-kort ↔ backlog-item (id-koppling i frontmatter);
  tvåvägs med konfliktdetektion (senast ändrad vinner + logg). Owner styr.
- **Notes-synk:** Nextcloud Notes ↔ `memory/`-noter; markdown åt båda håll.
- Synk körs via schemaläggaren (#1) eller på begäran (`deck_sync`, `notes_sync`).

## 8. Dokumentgenerering (Collabora/OnlyOffice)

Statusrapporter (#PM) och mötesnoteringar kan skrivas som riktiga `.odt/.docx` i
Nextcloud via `files_write` + en mall; delas som Nextcloud-länk. Lågt prioriterat men
högt upplevt värde för intressent-kommunikation.

## 9. Säkerhet & integritet

- **Per-user isolering:** varje användare kopplar sitt eget Nextcloud-konto; adaptern
  väljer rätt token (connector-ramverkets `per_user`). En användare når aldrig annans.
- **Credentials serverside** via token-store/`config.secret`; aldrig mot AI:n/loggar.
- **ACL + path-validering** på filer som för lokal vault; indexering respekterar
  behörighet (semantisk sökning #2 filtrerar per roll).
- **Utgående via Utkorgen (#3):** `chat_post`, Deck-skrivningar och delningslänkar
  gate:as i review-läge.
- **Datahemvist:** allt stannar i kundens Nextcloud (self-host-löftet) — dokumentera.

## Byggordning

1. **WebDAV FilesBackend** — bakom connector-ramverket; + indexeringshook (#2).
2. **CardDAV ContactsBackend** — `contacts_search/get` + kontaktupplösning i mail/brief.
3. **Talk ChatBackend** — `chat_post/read` + registrera som notiskanal (#1).
4. **Tasks (CalDAV VTODO)** — `tasks_*`.
5. **Deck-synk / Notes-synk** — schemalagd tvåvägs.
6. **Dokumentgenerering** — mallar → .odt/.docx via WebDAV.
7. **Config + docs.**
8. **CI** — grönt.

---

## Utvecklingsinstruktioner

Förutsätter connector-ramverket ([FEATURE-CONNECTOR-FRAMEWORK.md](FEATURE-CONNECTOR-FRAMEWORK.md)).
Konventioner: se [FEATURE-PROACTIVE-BRIEF.md](FEATURE-PROACTIVE-BRIEF.md). Kör
`python -m pytest -q` från `gateway/`. HTTP-anrop injicerbara (mocka i test — ingen
riktig Nextcloud i CI).

### Steg 1 — WebDAV FilesBackend
`connectors/adapters/files_webdav.py` som uppfyller `FilesBackend`; PROPFIND för
`list`, GET för `read`, PUT för `write`, sök via listning + innehållsmatch. Auth via
injicerad HTTP-klient + credential. Registrera `ConnectorSpec(type='webdav',
capability='files')`. **Test** (`tests/test_nc_files.py`): list/read/write mot mockad
WebDAV; path-traversal blockeras (`paths.py`); stora/binära filer hoppas i sök.

### Steg 2 — Indexeringshook
Koppla WebDAV-filer till #2:s `reindex_project`/`index_upsert` (skip-lista + storlekstak).
**Test:** en indexerad Nextcloud-fil hittas via `search_all` (fejk-embedder).

### Steg 3 — CardDAV ContactsBackend
`connectors/adapters/contacts_carddav.py`; `contacts_search(query)`/`get(id)` via
REPORT/PROPFIND, parsa vCard (återanvänd `vobject`). MCP-verktyg `contacts_search`,
`contacts_get` (via `_tool_call`). Kontaktupplösning: en hjälpare `resolve_sender(email)`
som mail/brief kan kalla. **Test** (`tests/test_nc_contacts.py`): sök på namn/e-post
mot mockad vCard-respons; resolve returnerar namn för känd adress.

### Steg 4 — Talk ChatBackend
`connectors/adapters/chat_nextcloud_talk.py`; `post/read` via OCS (`OCS-APIRequest`-
header). MCP-verktyg `chat_post`/`chat_read`. Registrera `{"type":"nextcloud_talk"}`
som notiskanal i #1:s `build_channels`. Utgående `chat_post` går via Utkorgen (#3).
**Test** (`tests/test_nc_talk.py`): post POST:ar rätt payload; notiskanal levererar via
mockad klient; review-läge köar istället för att posta.

### Steg 5 — Tasks (CalDAV VTODO)
`connectors/adapters/tasks_caldav.py`; `tasks_list/add/complete`. **Test:** VTODO
skapas/listas mot mockad CalDAV.

### Steg 6 — Deck / Notes-synk
`nextcloud/sync.py`: `deck_sync(project)` och `notes_sync(project)` med id-koppling i
frontmatter + konfliktregel (senast ändrad + logg). Körs via schemaläggaren (#1) eller
verktyg (owner). **Test** (`tests/test_nc_sync.py`): nytt Deck-kort → backlog-item;
ändring på båda håll → konflikt loggas, senast ändrad vinner.

### Steg 7 — Dokumentgenerering
Mall → `.odt/.docx` (t.ex. via en enkel mall + `files_write` till WebDAV). **Test:**
en statusrapport skrivs som fil i mockad WebDAV.

### Steg 8 — Config + docs
Utöka `acl.example.yaml` med Nextcloud-resurser (files/contacts/tasks/talk) och
`defaults.nextcloud_base_url` (SELF-HOST-STACK.md). Registrera doket i `docs/INDEX.md`
(gjort); länka från SELF-HOST-STACK.md.

### Steg 9 — Kör allt
`cd gateway && python -m pytest -q` + `python3 scripts/check-docs-index.py`.

### Acceptanskriterier
- [ ] `files_*` fungerar mot Nextcloud WebDAV via connector-ramverket; filerna blir sökbara (#2).
- [ ] `contacts_search` löser upp avsändare så brief/mail kan visa namn istället för adress.
- [ ] `chat_post`/`chat_read` mot Talk fungerar; Talk kan väljas som notiskanal i briefen (#1).
- [ ] Tasks (VTODO), Deck-synk och Notes-synk fungerar med konfliktregel och owner-styrning.
- [ ] Per-user: varje användare når bara sitt eget Nextcloud-konto; credentials aldrig mot AI:n.
- [ ] Utgående (chat/Deck/delning) går via Utkorgen (#3) i review-läge; path-traversal blockeras; hela sviten + docs-index grön.

---

## Framtided arbete
- Nextcloud som SSO/identitetskälla (koppla `oauth_sub` ↔ Nextcloud-användare).
- Full-text-sök via Nextcloud egna index istället för att dra ner filer.
- Bevaka Nextcloud-aktivitet (aktivitets-API) → interna events för regler (#4).
- Managed/extern Nextcloud-topologi vid större team (SELF-HOST-STACK.md).
