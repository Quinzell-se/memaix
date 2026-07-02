# Funktion #7 — Connector-ramverk (pluggbara backend-adaptrar)

SPDX-License-Identifier: AGPL-3.0-or-later

Designdok + byggspec för ett **pluggbart connector-ramverk**: ett enhetligt
adapter-gränssnitt så att nya integrationer (Microsoft Graph, Gmail, Nextcloud,
Slack, Jira, mötestranskript …) läggs till som *plugins* istället för
engångslösningar. Realiserar och generaliserar adaptermodellen i
[BACKENDS.md](BACKENDS.md).

Byggs stegvis enligt [Byggordning](#byggordning) och
[Utvecklingsinstruktioner](#utvecklingsinstruktioner). Detta är grunden i fas 4
(se [ROADMAP.md](ROADMAP.md)) och en förutsättning för Nextcloud-fördjupningen
([FEATURE-NEXTCLOUD-BACKEND.md](FEATURE-NEXTCLOUD-BACKEND.md)).

---

## 1. Problemet

Idag är backend-valet hårdkopplat i verktygen: `email.py` skapar `imap_tools.MailBox`
direkt, `calendar.py` har `_RealDavAdapter`/`_PerUserGoogleAdapter` inline, `files.py`
kan bara lokal vault. Varje ny tjänst kräver att man petar i verktygsfilerna. Med ett
ramverk blir en integration en självständig modul som *registrerar* sig — verktygen
rör man aldrig igen.

## 2. Nyckelbeslut

1. **Kapabilitets-gränssnitt, inte tjänst-gränssnitt.** Definiera små protokoll per
   *kapabilitet* — `MailBackend`, `CalendarBackend`, `FilesBackend`, `ContactsBackend`,
   `ChatBackend`, `IssueBackend` — som verktygen pratar med. En tjänst (Google,
   Nextcloud …) implementerar de kapabiliteter den stöder.
2. **Registret väljer adapter per projekt-resurs.** `acl.yaml`/`memaix.yaml` anger
   `type` per resurs (som redan i BACKENDS.md); en `ConnectorRegistry` mappar
   `type → factory` och bygger rätt adapter, med credentials via `config.secret`
   eller per-user token-store.
3. **Befintliga verktyg blir tunna.** `email_*`/`calendar_*`/`files_*` slutar
   instansiera backends själva och kallar `registry.get(project, "mail", user)`.
   Nuvarande IMAP/CalDAV/WebDAV/Google flyttas in som adaptrar bakom samma protokoll
   — beteendet är oförändrat (befintliga tester ska passera).
4. **Nya kapabiliteter är opt-in.** `ChatBackend`/`IssueBackend` m.fl. läggs till utan
   att röra kärnan; nya MCP-verktyg (t.ex. `chat_post`) läggs bredvid.
5. **Per-user och delat samexisterar.** En adapter deklarerar sin auth-modell
   (`shared` via `*_ref` eller `per_user` via token-store); registret väljer rätt
   token utifrån den inloggade användaren (BACKENDS.md §Auth).

## 3. Översikt

```
  email_* / calendar_* / files_* / (nya) chat_* / issue_*      (MCP-verktyg)
        │  registry.get(project, capability, user)
        ▼
  ConnectorRegistry   type → factory   (+ auth: shared | per_user)
        │
        ├─ mail:     imap · google · microsoft
        ├─ calendar: caldav · google · microsoft
        ├─ files:    webdav · local · google_drive · onedrive
        ├─ contacts: carddav · google · microsoft
        ├─ chat:     slack · nextcloud_talk · telegram
        └─ issues:   jira · linear · github
        │  varje adapter: credentials via config.secret / token_store
        ▼
  Adapter (implementerar kapabilitets-protokollet)
```

## 4. Kapabilitets-protokoll

`connectors/base.py` — Protocol per kapabilitet (duck-typat, som dagens `_dav`/`_imap`):

```python
class MailBackend(Protocol):
    def list(self, folder: str, limit: int) -> list[dict]: ...
    def read(self, uid: str) -> dict: ...
    def search(self, query: str, limit: int) -> list[dict]: ...
    def append_draft(self, msg_bytes: bytes) -> None: ...
    def send(self, msg) -> None: ...

class CalendarBackend(Protocol):    # motsvarar dagens _dav-duck-typ
    def list_events(self, start, end) -> list[dict]: ...
    def create_event(self, ...) -> dict: ...
    def update_event(self, id, **fields) -> dict: ...
    def delete_event(self, id) -> None: ...

class FilesBackend(Protocol):   list/read/write/search  (motsvarar files.py)
class ContactsBackend(Protocol): search(query) -> list[dict]; get(id) -> dict
class ChatBackend(Protocol):     post(channel, text); list_messages(channel, since)
class IssueBackend(Protocol):    list(query); create(item); update(id, **fields)
```

Gränssnitten speglar **dagens** verktyg exakt där de finns (mail/calendar/files), så
att flytten är en refaktor utan beteendeändring.

## 5. Register & factory

`connectors/registry.py`:

```python
@dataclass(frozen=True)
class ConnectorSpec:
    type: str                    # 'imap' | 'google' | 'nextcloud_talk' | ...
    capability: str              # 'mail' | 'calendar' | 'files' | 'contacts' | 'chat' | 'issues'
    auth: str                    # 'shared' | 'per_user'
    factory: Callable            # (resource_cfg, *, secret, token, user) -> adapter

class ConnectorRegistry:
    def register(self, spec: ConnectorSpec) -> None
    def get(self, acl, cfg, token_store, project, capability, user):
        """Slå upp projektets resurs-cfg, välj type→spec, lös credentials, bygg adapter.
        auth='shared' → config.secret(resource['*_ref']); auth='per_user' →
        token_store.load_one(user, provider, account)."""
```

Adaptrar registrerar sig i `connectors/catalog.py` (importeras vid uppstart) —
samma självregistrerings-mönster som förmåge-registret (#6).

## 6. Migrering av befintliga verktyg (ingen beteendeändring)

- `calendar.py`: flytta `_RealDavAdapter`, `_PerUserGoogleAdapter`, `_ICalAdapter`,
  `_FreeBusyAdapter` till `connectors/adapters/` och registrera dem. `_resolve_calendar_dav`
  i `server.py` blir `registry.get(..., "calendar", user)` (behåll `CalendarAuthRequired`).
- `email.py`: bryt ut `_make_mailbox` → en `imap`-adapter (`MailBackend`); `email_*`
  kallar `registry.get(..., "mail", user)`. Behåll `_imap`-injektionen för test.
- `files.py`: nuvarande lokal-vault blir en `local` `FilesBackend`; WebDAV/Drive/OneDrive
  läggs till som nya adaptrar (Nextcloud i nästa spec).
- Nya kapabiliteter (`chat`, `issues`, `contacts`) får nya MCP-verktyg i egna PR:er.

## 7. Nya integrationer (efter ramverket)

Prioriterad ordning (var och en = en adapter + ev. nya verktyg, isolerat testbar):
1. **Microsoft Graph** (mail/calendar/files) — störst affärsmarknad (BACKENDS.md fas 2).
2. **Google** (Gmail/Calendar/Drive) — utöka nuvarande kalender-Google till mail/filer.
3. **Nextcloud** (files/contacts/chat) — [FEATURE-NEXTCLOUD-BACKEND.md](FEATURE-NEXTCLOUD-BACKEND.md).
4. **Chat** (Slack/Telegram) — `chat_post`/`chat_read`; dubblar som notiskanal (#1).
5. **Issues** (Jira/Linear/GitHub) — `issue_*`, tvåvägssynk mot backlog.
6. **Mötestranskript** — en `TranscriptSource` som matar text → #2-index + #4-regler.

## 8. Säkerhet & integritet

- **Credentials aldrig mot AI:n** — adaptrar hämtar hemligheter via `config.secret`/
  token-store serverside (BACKENDS.md-principen); loggas aldrig.
- **Per-user isolering** — `auth='per_user'` väljer token för den inloggade användaren;
  fel användare kan aldrig nå annans token (samma ACL som idag).
- **Feltålighet** — adapterfel isoleras per anrop (timeout + tydligt fel), fäller inte
  gatewayen. Retry/backoff för nätverksanrop.
- **Utgående via Utkorgen** — `chat_post`, `issue_create`, `email_send` m.fl. som är
  utgående går genom Utkorgen (#3) när projektet är i `review`.
- **Datahemvist** — dokumentera per adapter var datan ligger (BACKENDS.md §Ärlig avvägning).

## Byggordning

1. **Protokoll** (`connectors/base.py`) — kapabilitets-Protocols.
2. **Register** (`connectors/registry.py`) — spec, register, `get` med auth-val.
3. **Migrera kalender** — flytta adaptrarna, koppla `server._resolve_calendar_dav`.
4. **Migrera mail + files(local)** — bakom registret; befintliga tester oförändrade.
5. **Katalog** (`connectors/catalog.py`) — självregistrering vid uppstart.
6. **Första nya adapter** (Microsoft Graph *eller* Nextcloud) som bevis på pluggbarhet.
7. **Config + docs** — utöka `acl.example.yaml`-resursformatet (finns i BACKENDS.md).
8. **CI** — grönt.

---

## Utvecklingsinstruktioner

Konventioner: se [FEATURE-PROACTIVE-BRIEF.md](FEATURE-PROACTIVE-BRIEF.md). Kör
`python -m pytest -q` från `gateway/`. **Kritiskt: fas 3–4 får inte ändra
beteende** — befintliga `test_email.py`/`test_calendar.py` ska passera oförändrade.

### Steg 1 — `connectors/base.py`
Paket `connectors/__init__.py` + Protocols enligt §4. Spegla dagens `_dav`/`_imap`-
duck-typer exakt. **Test** (`tests/test_connectors_base.py`): en minimal fejk-adapter
uppfyller `MailBackend`/`CalendarBackend` (strukturellt).

### Steg 2 — `connectors/registry.py`
`ConnectorSpec`, `ConnectorRegistry.register/get`. `get` läser `acl.resource(project,
capability)`, väljer `type`, löser credentials (`shared`→`config.secret(cfg['*_ref'])`,
`per_user`→`token_store.load_one`), bygger adaptern via factory. Injicerbara
`config`/`token_store` för test. **Test** (`tests/test_connectors_registry.py`):
`type='imap'` bygger imap-adapter med rätt secret; okänd type → tydligt fel;
`per_user` utan token → `CalendarAuthRequired`/None enligt kapabilitet.

### Steg 3 — Migrera kalender
Flytta de fyra kalenderadaptrarna till `connectors/adapters/calendar_*.py`, registrera
dem, och låt `server._resolve_calendar_dav` delegera till `registry.get(...,'calendar',user)`.
**Test:** hela `test_calendar.py` passerar oförändrat; ett nytt test bygger adaptern via
registret.

### Steg 4 — Migrera mail + files(local)
✅ **Mail:** `server.py`'s `email_list`/`email_read`/`email_search`/
`email_create_draft` resolverar mailboxen via `registry.get(...,"mail",user)`
(en `_with_mail_backend`-wrapper som håller resolutionen innanför
`_audited`'s try/except, så ett okonfigurerat projekt fortfarande
audit-loggas identiskt med innan). `email_send` rör SMTP direkt — inte en
registrerad kapabilitet, orört. `tools/email.py`'s egna `_make_mailbox` finns
kvar oförändrad (används fortfarande av `catalog.py`'s `imap`-factory och
som fallback när `_imap` inte injiceras, t.ex. i enhetstester som kallar
`tools/email.py` direkt). **Test:** `test_email.py` oförändrat;
`test_email_server.py` nytt, täcker registret-bygget på server-lagret.

**Files(local) — avsiktligt inte migrerat, inte glömt:** `"files"`-kapabiliteten
är redan upptagen av Nextcloud-WebDAV (`nc_files_*`, se
FEATURE-NEXTCLOUD-BACKEND.md); den lokala valvet har en helt annan resursform
(bar sökväg i `acl.yaml`, inte `{type,url,...}`) och är en *ytterligare*
filkälla, inte samma kapabilitet under ett nytt namn. Att flytta
`tools/files.py` hit skulle antingen kollidera med webdav-resursen eller
kräva en ny kapabilitetsnyckel (`"vault"`) + schemaändring i `acl.yaml` —
ett produktbeslut, inte en mekanisk refaktor, så det lämnas som öppet
framtida arbete istället för att gissas fram.

### Steg 5 — `connectors/catalog.py`
Självregistrera alla inbyggda adaptrar; importera från `server.py`. **Test:**
katalogen registrerar minst imap/caldav/google/local; `registry.get` hittar dem.

### Steg 6 — Första nya adapter (bevis)
Implementera **Microsoft Graph mail** *eller* peka på Nextcloud-specen som första
externa. Isolerat testbar med mockad HTTP. **Test:** list/read via mockad Graph-svar.

### Steg 7 — Config + docs
Bekräfta att `acl.example.yaml`-resursformatet (BACKENDS.md §Config) räcker; lägg
ev. `auth: per_user`-flagga per resurs. Registrera doket i `docs/INDEX.md` (gjort);
uppdatera BACKENDS.md-fasrutan att peka hit.

### Steg 8 — Kör allt
`cd gateway && python -m pytest -q` + `python3 scripts/check-docs-index.py`.

### Acceptanskriterier
- [x] `email_*` fungerar oförändrat via registret (befintliga tester gröna); `calendar_*` kvar
      (dokumenterat skäl ovan), `files_*` (lokal vault) migreras inte hit (dokumenterat skäl ovan).
- [x] En ny adapter läggs till genom att registrera en `ConnectorSpec` — utan att röra verktygsfilerna
      (visat av contacts/webdav-files/tasks/deck/notes-adaptrarna, alla tillagda utan ändringar i
      `server.py`'s befintliga `email_*`/`calendar_*`-verktyg).
- [ ] Ett projekt kör IMAP-mail, ett annat Google-kalender, samtidigt (registret väljer per resurs).
- [ ] `per_user`-adapter väljer rätt token för inloggad användare; fel användare når aldrig annans token.
- [ ] Utgående adapter-åtgärder (chat/issue/mail-send) går via Utkorgen (#3) i review-läge.
- [ ] Credentials exponeras aldrig mot AI:n/loggar; adapterfel isoleras; hela sviten + docs-index grön.

---

## Framtida arbete
- Adapter-SDK dokumenterad för tredjepart (skriv din egen connector).
- Health-/capability-introspektion per adapter (visas i förmåge-registret #6).
- Rate-limit/kvot per extern tjänst (respektera API-gränser).
- OAuth-app-registrering guidas av wizarden (BACKENDS.md fas 5).
