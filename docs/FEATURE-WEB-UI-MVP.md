# Funktion #22+23 — Webb-UI MVP (Fas A + Fas B)

SPDX-License-Identifier: AGPL-3.0-or-later

Designdok + byggspec för Memaix webb-UI MVP: det mörka app-skalet med sidebar,
rollmedveten board, inställningssida med OAuth-länkflöde, minnesutforskare och
per-user-inloggning via `acl.yaml`. Fas A (MEX-022) levererar fundament + board i
app-shellet. Fas B (MEX-023) levererar inställningar, minnesutforskaren och
per-user-lösenord. Dokumentet täcker båda faserna i en sammanhållen byggspec —
båda ska vara gröna innan Fas C (MEX-024, utkorgs-UI + admin) påbörjas.

Fundament-arkitekturen (CSS-tokens, `_html_with_locale`, `api()`, `shell.html`)
är specad i `FEATURE-WEB-UI-FOUNDATION.md` (MEX-022 Fas A). Det här dokumentet
beskriver Fas B-komponenterna i detalj och sammanfattar Fas A-kraven i den
gemensamma acceptansmatrisen.

---

## 1. Vad användaren upplever

### 1.1 Board i app-shellet

Användaren navigerar till `/app/board` (eller klickar "Board" i sidebaren) och
ser Kanban-brädet i det mörka skalet — identisk funktionalitet som `/board`
idag men i mörkt tema och med rollmedvetet drag. Gamla URL:en `/board` returnerar
301 → `/app/board` utan att bokmärken bryts.

Drag-och-släpp är aktiverat enbart för owner och admin: drags `draggable`-attribut
sätts av `board.js` baserat på `me.role_map[project]`. En reader eller collaborator
ser ett drag-handtag med tooltip "Kräver owner-roll" men kan inte faktiskt flytta.

### 1.2 Inställningar — flik Konton

Användaren öppnar `/app/settings` och ser tre flikar: Konton, Profil, Brief. På
fliken Konton listas alla möjliga leverantörer (Google, Microsoft — Microsoft är
gråmarkerad "Kommer snart"). Google-raden visar statusdot:

- `linked` → grön dot, e-postadress, knapp "Koppla ur"
- `needs_relink` → gul dot, text "Åtkomsttokens har gått ut", knapp "Koppla om"
- `not_linked` → grå dot, knapp "Koppla Google"

Klick på "Koppla Google" → `GET /app/api/accounts/link/google` hämtar auth-URL →
`window.open(url, '_blank', 'width=600,height=700')` öppnar OAuth-flödet. Settings-
sidan startar en 3-sekunders poll mot `GET /app/api/accounts` i max 2 minuter;
när leverantören dyker upp med `linked` stoppas pollingen och statusdoten uppdateras
utan sidladdning.

Under konto-listan: **Kalenderläge** per projekt — en `<select>` med alternativen
`oauth` (Använd kopplat Google-konto), `ical_secret` (privat iCal-URL),
`free_busy` (Visa/dölj — ej händelsedetaljer), `none` (Inaktiverat). Val sparas
via `POST /app/api/settings/calendar-mode`. En förklaring av varje alternativ
visas som disabled i select-alternativets title-attribut, inte som flytande text.

### 1.3 Inställningar — flik Profil

Skrivskyddad vy av `shared/om-{user}.md` ur minnesvaulten. Innehållet renderas
med `mdView()`. En status-chip visar onboarding-stadiet (hämtat från
`me.onboarding_missing`): "Komplett ✓" (grön) eller "Onboarding saknas" (gul).

En not under innehållet: *"Din profil uppdateras av AI-assistenten, inte här."*
Ingen redigeringsknapp.

### 1.4 Inställningar — flik Brief

Platshållarvy med texten *"Brief-inställningar — kommer i Fas D."* En länk till
`FEATURE-PROACTIVE-BRIEF.md`. Fliken är synlig men inaktiv innehållsmässigt.

### 1.5 Minnesutforskaren

Användaren öppnar `/app/memory?project=acme` och ser ett delat vy: till vänster
ett filträd med alla markdown-noter i projektets vault (hierarkiskt, undermappar
expanderbara), till höger en filvisare med markdown-renderat innehåll.

Sökrutan ovanför trädet träffar `GET /app/api/memory/search?q=…&project=acme`.
Resultat visas som en platt lista med filnamn + matchande utdrag (med `<mark>`-
markering); klick på ett resultat öppnar filen i visaren.

"Historik"-knappen bredvid filnamnet öppnar en drawer på höger sida med projektets
git-commits (filtrerade på den valda filen om möjligt, annars alla). Varje commit
visar: SHA (7 tecken), commit-meddelande, relativ tid ("3 h sedan", "igår"). En
"Återställ hit"-knapp per commit öppnar en bekräftelsedialog:

> Återställa `decisions.md` till commit `a1b2c3d` (3 h sedan)?
> Det nuvarande innehållet skrivs över i vaulten och ett nytt git-commit skapas.
> [Avbryt] [Återställ]

"Återställ" → `POST /app/api/memory/revert` med `{project, file, sha}` → visar
toast "Återställt. Nytt commit: e4f5a6b." och laddar om filvisaren.

### 1.6 Per-user-inloggning

Login-appen verifierar mot `password_hash` i `acl.yaml` per användare istället
för den delade `MEMAIX_LOGIN_PASSWORD_HASH`. En användare som saknar `password_hash`
kan inte logga in via webb-UI:t (MCP-tokenauth påverkas inte).

---

## 2. Nyckelbeslut

1. **Per-user `password_hash` i `acl.yaml`.** `login-app/app.py` läser användarens
   egen hash om den finns; faller annars tillbaka på miljövariabeln (bakåtkompat).
   Hash-format: `bcrypt` via `passlib[bcrypt]`, samma som login-appar normalt
   använder. Admin-CLI för att generera: `python -m memaix_gateway.cli hash-password`.

2. **OAuth-länkflödet sker i nytt fönster, inte redirect.** Settings-sidan förblir
   öppen och pollar; inget state går förlorat. Det befintliga `/link/google` och
   callback-flödet berörs inte — callback-sidan får en "Tillbaka"-länk till
   `/app/settings`.

3. **Minnesutforskaren är skrivskyddad.** Skrivning sker via MCP-verktyg (AI:ns
   jobb). UI:t är insyn och revision — inte en editor. "Återställ hit" är det
   enda skrivande flödet och kräver explicit bekräftelse + ägarroll.

4. **`memory.py`-funktionerna anropas direkt.** `GET /app/api/memory/notes` anropar
   `memory_list(acl, user, project)` — samma funktion som MCP-verktyget. Ingen
   parallell implementation. Samma gäller `memory_search`, `memory_read`,
   `memory_history` och `memory_revert`. Invariant: webb-UI är ett tunt HTTP-lager
   ovanpå exakta samma tool-funktioner som MCP.

5. **Kalenderläge lagras i `acl.yaml` per projekt per användare** (under
   `users.{user}.calendar_mode.{project}`). `calendar.py`-funktionen `get_status()`
   och `setup_mode()` används direkt.

6. **`account.py`-funktionerna anropas direkt.** `account_list(acl, user)` →
   `GET /app/api/accounts`, `account_link(acl, user, provider)` → URL-svar,
   `account_unlink(acl, user, provider)` → `DELETE /app/api/accounts/{provider}`.

7. **Rollkontroll i board: client-side toggle + server-side enforce.** `me.role_map`
   styr `draggable`-attributet i JS. Server-side `board/routes.py` PATCH enforce:ar
   redan `owner` — det ändras inte. Client-side är UX, server-side är säkerhet.

8. **Git-historik via `subprocess git log`.** `memory_history(project, file=None)`
   kör `git log --oneline -50 -- {file}` i vault-katalogen. Revert via `git checkout
   {sha} -- {file} && git commit`. Ingen ny dependency.

---

## 3. Översikt

```
Browser                          Gateway (Starlette)
───────                          ───────────────────
GET /app/board    ─────────────► web/routes.py → _html_with_locale("board")
                                 board.html inbäddat i app-shell
GET /board        ─────────────► 301 → /app/board

GET /app/settings ─────────────► _html_with_locale("settings")
                  ◄─────────────  tre flikar, kontorad/statusdot/kalenderval
  JS: poll /app/api/accounts (3s)
     ──────────────────────────►  GET /app/api/accounts
                  ◄──────────────  [{provider, status, email}]
  "Koppla Google" klick:
     window.open(link_url)  ────► GET /app/api/accounts/link/google
                                  account_link(acl, user, "google")
                  ◄──────────────  {url: "https://accounts.google.com/..."}
  /link/google callback ─────────► befintlig login-app OAuth-callback
                  ◄──────────────  "Konto kopplat. Tillbaka till inställningar."

GET /app/memory   ─────────────► _html_with_locale("memory")
  JS: filträd + visare
     ──────────────────────────►  GET /app/api/memory/notes?project=acme
                  ◄──────────────  [{path, mtime}]  ← memory_list()
     ──────────────────────────►  GET /app/api/memory/note?project=acme&path=x.md
                  ◄──────────────  {content}  ← memory_read()
     ──────────────────────────►  GET /app/api/memory/search?q=&project=acme
                  ◄──────────────  [{path, excerpt}]  ← memory_search()
  Historik-drawer:
     ──────────────────────────►  GET /app/api/memory/history?project=acme&path=x.md
                  ◄──────────────  [{sha, msg, ts_iso}]  ← memory_history()
  Återställ:
     ──────────────────────────►  POST /app/api/memory/revert
                                  {project, file, sha}  ← memory_revert()
                  ◄──────────────  {new_sha}

POST /login       ─────────────► login-app/app.py
                                 users.{user}.password_hash (acl.yaml)
                                 fallback: MEMAIX_LOGIN_PASSWORD_HASH
```

---

## 4. Komponenter

### 4.1 Board i app-shell (`web/pages/board.html`)

En tunn HTML-wrapper som inkluderar `board/board.html`-innehållet inuti
`<!--MEMAIX_CONTENT-->`-sloten i shell:en. I praktiken: `web/routes.py`
`app_page("board")` läser `web/pages/board.html`, som i sin tur innehåller
ett `<div id="board-mount">` dit `board.js` renderar sin markup.

Alternativ implementation: `web/routes.py` PATCH `/app/board`-routen till att
anropa `board/routes.py`-handlern och wrappa svaret i shell-HTML. Enklast i
praktiken är att `board.html` laddas som en `<iframe src="/board/inner">` i
main-sloten, och `/board/inner` returnerar board-HTML utan shell. Välj
iframe-metoden i Fas A för att minimera board-kodröran; ersätt med inline i Fas D.

**Rollmedvetet drag:**

```js
// board.js (tillägg, Fas B)
async function applyRoleDrag(project) {
  const me = await api('GET', '/app/api/me');
  const role = me.role_map[project] ?? 'reader';
  const canDrag = role === 'owner' || me.is_admin;
  document.querySelectorAll('.card[draggable]').forEach(el => {
    el.draggable = canDrag;
    if (!canDrag) {
      el.title = t('drag_requires_owner');
      el.classList.add('drag-disabled');
    }
  });
}
```

`.drag-disabled` i CSS: `cursor: not-allowed; opacity: 0.85;` på drag-handtaget.

### 4.2 `web/pages/settings.html` + `web/static/settings.js`

**HTML-struktur:**

```html
<div class="tabs" role="tablist">
  <button class="tab-active" data-tab="accounts">Konton</button>
  <button data-tab="profile">Profil</button>
  <button data-tab="brief">Brief</button>
</div>
<div id="tab-accounts" class="tab-panel"> … </div>
<div id="tab-profile"  class="tab-panel" hidden> … </div>
<div id="tab-brief"    class="tab-panel" hidden> … </div>
```

Tab-switching: ren JS, inga animationer, `hidden`-attribut toggles.

**Flik Konton — kontorad-template:**

```html
<div class="account-row" data-provider="google">
  <span class="status-dot" data-status="not_linked"></span>
  <span class="provider-name">Google</span>
  <span class="account-email muted"></span>
  <div class="account-actions">
    <button class="btn btn-primary link-btn" hidden>Koppla Google</button>
    <button class="btn btn-danger unlink-btn" hidden>Koppla ur</button>
  </div>
</div>
```

`status-dot` CSS: `width:8px; height:8px; border-radius:50%; display:inline-block;`
med `[data-status=linked]{background:var(--success)}`,
`[data-status=needs_relink]{background:var(--warning)}`,
`[data-status=not_linked]{background:var(--muted)}`.

**Poll-flöde i `settings.js`:**

```js
let linkPoll = null;

async function startLinkPoll(provider) {
  const start = Date.now();
  linkPoll = setInterval(async () => {
    if (Date.now() - start > 120_000) { clearInterval(linkPoll); return; }
    if (document.visibilityState === 'hidden') return;
    const accounts = await api('GET', '/app/api/accounts');
    const row = accounts.find(a => a.provider === provider);
    if (row?.status === 'linked') {
      clearInterval(linkPoll);
      renderAccountRow(row);
      toast(t('account_linked_ok'), 'success');
    }
  }, 3000);
}

document.querySelector('[data-provider=google] .link-btn')
  ?.addEventListener('click', async () => {
    const { url } = await api('GET', '/app/api/accounts/link/google');
    window.open(url, '_blank', 'width=600,height=700');
    startLinkPoll('google');
  });
```

**Kalenderläge-sektion:**

Renderas under konto-listan. Hämtar valt projekt från `localStorage.memaix_project`.

```html
<div class="calendar-mode-section surface">
  <h3>Kalenderläge — <span id="cal-project-name"></span></h3>
  <select id="cal-mode-select">
    <option value="oauth">OAuth — Använd kopplat Google-konto</option>
    <option value="ical_secret">Privat iCal-URL</option>
    <option value="free_busy">FreeBusy — visa/dölj (inga detaljer)</option>
    <option value="none">Inaktiverat</option>
  </select>
  <p class="muted" id="cal-mode-hint"></p>
</div>
```

`settings.js` hämtar `GET /app/api/settings/calendar-mode?project=X` vid load,
sätter `<select>`-värdet. Vid ändring: `POST /app/api/settings/calendar-mode`
med `{project, mode}` → anropar `calendar.setup_mode(acl, user, project, mode)`.

**Flik Profil:**

```js
async function loadProfile() {
  const { content, onboarding_missing } = await api('GET', '/app/api/memory/profile');
  mdView(document.querySelector('#profile-content'), content);
  const chip = document.querySelector('#onboarding-chip');
  chip.textContent = onboarding_missing ? t('onboarding_missing') : t('onboarding_complete');
  chip.dataset.status = onboarding_missing ? 'warning' : 'ok';
}
```

`#onboarding-chip[data-status=ok]` → `background:var(--success)`,
`[data-status=warning]` → `background:var(--warning)`.

### 4.3 `web/pages/memory.html` + `web/static/memory.js`

**Layout (desktop):**

```
┌──────────────────────────────────────────────────────┐
│ [🔍 Sök i minnet…]                    [projekt ▾]    │
├───────────────────────┬──────────────────────────────┤
│ Filträd (240px)       │ Filvisare                    │
│                       │ ┌──────────────────────────┐ │
│ ▸ decisions.md        │ │ decisions.md  [Historik]  │ │
│ ▼ kund-x/            │ │                           │ │
│     brief.md          │ │ # Beslut…                 │ │
│     kontakt.md        │ │                           │ │
│ ▸ om-alice.md         │ │ (markdown renderat)       │ │
│                       │ └──────────────────────────┘ │
└───────────────────────┴──────────────────────────────┘
```

**Filträd:** byggs som `<ul class="file-tree">` med `<details>`-element för
undermappar. Klass `.file-tree-item.active` på vald fil. Klick → läs fil + uppdatera
visaren. Inget lazy-load i MVP — alla sökvägar laddas på en gång.

**Sök:** `<input id="memory-search" type="search">` med 300ms debounce.
Sökresultat ersätter filträdet med en platt lista. Utdragen highlightas:

```js
function highlight(text, q) {
  const re = new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
  const el = document.createElement('span');
  // bygg DOM-noder med textContent — ingen innerHTML med sökvärde
  text.replace(re, (m, offset) => { /* ... */ });
  return el;
}
```

**Historik-drawer:**

```html
<div id="history-drawer" class="drawer" hidden>
  <div class="drawer-header">
    <h3>Historik — <span id="history-filename"></span></h3>
    <button class="btn" id="close-drawer">✕</button>
  </div>
  <ul id="history-list" class="commit-list"></ul>
</div>
```

`.drawer` CSS: `position:fixed; right:0; top:var(--topbar-h); height:calc(100vh - var(--topbar-h)); width:360px; background:var(--surface); border-left:1px solid var(--border); overflow-y:auto; z-index:200; transform:translateX(100%); transition:transform .2s;`

`[open]`-attribut på `.drawer` → `transform:translateX(0)`.

Commit-rad-template:

```html
<li class="commit-row">
  <code class="mono sha">a1b2c3d</code>
  <span class="commit-msg">Uppdaterade beslut om leverantör</span>
  <time class="muted">3 h sedan</time>
  <button class="btn revert-btn">Återställ hit</button>
</li>
```

Klick på "Återställ hit" → `modal(confirmHtml)` med bekräftelse → vid bekräftelse:
`api('POST', '/app/api/memory/revert', {project, file: currentFile, sha})` →
toast, stäng drawer, ladda om fil i visaren.

### 4.4 `web/api/memory.py` — Backend för minnesutforskaren

```python
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Webb-API-lager för minnesutforskaren — tunnt lager ovanpå tools/memory.py."""
from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse

from ..tools import memory as t_mem
from ..acl import Acl


async def api_memory_notes(request: Request) -> JSONResponse:
    """GET /app/api/memory/notes?project=X → [{path, mtime}]"""
    acl = Acl.from_config()
    user = _require_user(request)
    project = request.query_params.get("project") or _default_project(request, acl, user)
    acl.enforce(user, project, "reader")
    notes = t_mem.memory_list(acl, user, project)
    return JSONResponse(notes)


async def api_memory_note(request: Request) -> JSONResponse:
    """GET /app/api/memory/note?project=X&path=Y → {content}"""
    ...


async def api_memory_search(request: Request) -> JSONResponse:
    """GET /app/api/memory/search?project=X&q=Y → [{path, excerpt}]"""
    ...


async def api_memory_history(request: Request) -> JSONResponse:
    """GET /app/api/memory/history?project=X&path=Y → [{sha, msg, ts_iso}]"""
    ...


async def api_memory_revert(request: Request) -> JSONResponse:
    """POST /app/api/memory/revert {project, file, sha} → {new_sha}
    Kräver owner-roll.
    """
    acl = Acl.from_config()
    user = _require_user(request)
    body = await request.json()
    project, file, sha = body["project"], body["file"], body["sha"]
    acl.enforce(user, project, "owner")
    result = t_mem.memory_revert(acl, user, project, file, sha)
    return JSONResponse(result)


async def api_memory_profile(request: Request) -> JSONResponse:
    """GET /app/api/memory/profile → {content, onboarding_missing}"""
    ...
```

### 4.5 `web/api/accounts.py` — Backend för kontoinställningar

```python
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Webb-API för OAuth-konto-länkning — tunnt lager ovanpå tools/account.py."""
from __future__ import annotations

from ..tools import account as t_acc
from ..tools import calendar as t_cal


async def api_accounts_list(request: Request) -> JSONResponse:
    """GET /app/api/accounts → [{provider, status, email}]"""
    acl = Acl.from_config()
    user = _require_user(request)
    result = t_acc.account_list(acl, user)
    return JSONResponse(result)


async def api_accounts_link(request: Request) -> JSONResponse:
    """GET /app/api/accounts/link/{provider} → {url}"""
    provider = request.path_params["provider"]
    acl = Acl.from_config()
    user = _require_user(request)
    result = t_acc.account_link(acl, user, provider)
    return JSONResponse(result)


async def api_accounts_unlink(request: Request) -> JSONResponse:
    """DELETE /app/api/accounts/{provider} → {ok}"""
    provider = request.path_params["provider"]
    acl = Acl.from_config()
    user = _require_user(request)
    result = t_acc.account_unlink(acl, user, provider)
    return JSONResponse(result)


async def api_calendar_mode_get(request: Request) -> JSONResponse:
    """GET /app/api/settings/calendar-mode?project=X → {mode}"""
    ...


async def api_calendar_mode_set(request: Request) -> JSONResponse:
    """POST /app/api/settings/calendar-mode {project, mode}"""
    body = await request.json()
    project, mode = body["project"], body["mode"]
    acl = Acl.from_config()
    user = _require_user(request)
    result = t_cal.setup_mode(acl, user, project, mode)
    return JSONResponse(result)
```

### 4.6 Per-user-lösenord i `acl.yaml`

**Schema-tillägg:**

```yaml
# config/acl.example.yaml
users:
  alice:
    admin: true
    password_hash: "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/…"  # bcrypt
    oauth_subjects: [alice]
    grants:
      acme: owner
      project-a: collaborator
  bob:
    password_hash: "$2b$12$aBcD…"
    grants:
      acme: collaborator
```

`password_hash` är valfritt. Om det saknas: login-appen faller tillbaka på
`MEMAIX_LOGIN_PASSWORD_HASH` (ett delat lösenord) — bakåtkompatibelt.

**`login-app/app.py` — verifieringslogik:**

```python
def verify_password(username: str, password: str, acl_cfg: dict) -> bool:
    """Returnera True om lösenordet stämmer för användaren."""
    user_cfg = acl_cfg.get("users", {}).get(username, {})
    user_hash = user_cfg.get("password_hash")
    if user_hash:
        return bcrypt.checkpw(password.encode(), user_hash.encode())
    # bakåtkompatibelt: delat lösenord via miljövariabel
    shared_hash = os.environ.get("MEMAIX_LOGIN_PASSWORD_HASH", "")
    return shared_hash and bcrypt.checkpw(password.encode(), shared_hash.encode())
```

**CLI för att generera hash:**

```bash
python -m memaix_gateway.cli hash-password
# → Lösenord: (prompt, dolt)
# → Bekräfta: (prompt, dolt)
# → $2b$12$LQv3c1yqBWVHxkd0LHAkCO…
# Klistra in under users.{user}.password_hash i acl.yaml
```

Implementeras i `gateway/src/memaix_gateway/cli.py` som ett `argparse`-subkommando.
`passlib[bcrypt]` är redan ett beroende (login-appen). Om inte: lägg till i
`gateway/pyproject.toml`.

---

## 5. Backend-routes — komplett tabell

Alla `/app/api/*`-routes definieras i `web/routes.py` och delegerar till
identiska tool-funktioner som MCP-verktyget. Ingen logik dupliceras.

| Metod | Sökväg | Roll | Tool-funktion |
|-------|--------|------|---------------|
| GET | `/app/api/me` | autentiserad | `Acl.grants()`, `TokenStore` |
| GET | `/app/api/accounts` | autentiserad | `account_list()` |
| GET | `/app/api/accounts/link/{provider}` | autentiserad | `account_link()` |
| DELETE | `/app/api/accounts/{provider}` | autentiserad | `account_unlink()` |
| GET | `/app/api/settings/calendar-mode` | autentiserad | `calendar.get_status()` |
| POST | `/app/api/settings/calendar-mode` | autentiserad | `calendar.setup_mode()` |
| GET | `/app/api/memory/notes` | reader | `memory_list()` |
| GET | `/app/api/memory/note` | reader | `memory_read()` |
| GET | `/app/api/memory/search` | reader | `memory_search()` |
| GET | `/app/api/memory/history` | reader | `memory_history()` |
| POST | `/app/api/memory/revert` | owner | `memory_revert()` |
| GET | `/app/api/memory/profile` | autentiserad | `memory_read("shared/om-{user}.md")` |

**Sidesroutes (HTML):**

| Metod | Sökväg | Kommentar |
|-------|--------|-----------|
| GET | `/app` | Hem-dashboard |
| GET | `/app/board` | Board i app-shell |
| GET | `/app/settings` | Inställningar (3 flikar) |
| GET | `/app/memory` | Minnesutforskaren |
| GET | `/app/static/{path}` | Statiska tillgångar |
| GET | `/board` | 301 → `/app/board` |

**Felhantering:** alla `/app/api/*`-routes returnerar `{"error": "meddelande"}` med
lämplig HTTP-statuskod. `401` vid saknad session, `403` vid otillräcklig roll,
`404` om resurs saknas, `409` för konflikter, `500` med generellt felmeddelande
(inget stack-trace till klienten).

---

## 6. Byggordning

Bygg och verifiera i denna ordning. Varje steg ska vara självständigt grönt.

**Fas A (MEX-022) — fundament:**

1. `web/static/app.css` — design tokens + bas-klasser. Verifiera i DevTools.
2. `web/static/app.js` — `api()`, `toast()`, `modal()`, `mdView()`, `t()`,
   `pollBadge()`. Manuell verifiering i browser-konsolen.
3. `web/routes.py` — `_html_with_locale()`, `app_static`, `board_redirect` (301).
   `pytest tests/test_web_routes.py`.
4. `web/pages/shell.html` + `web/static/shell.js` — skelett utan innehåll.
   Ladda `/app`, bekräfta sidebar + topbar i mörkt tema.
5. `GET /app/api/me` — auth, Acl, TokenStore. `pytest tests/test_api_me.py`.
6. Sidebar-beteende i `shell.js` — toggle, localStorage, projektpicker, badges.
   Manuell verifiering.
7. `web/pages/home.html` + `web/static/home.js` — att-göra, projektkort, aktivitet.
   `pytest tests/test_web_home.py`.
8. Board-integration — `/board` → 301, `/app/board` i shell med rollmedvetet drag.
   Verifiera drag-lockout med en reader-session.
9. Mobil-layout — `@media`-regler, tab-bar. DevTools 375 px.
10. CI grön — `python -m pytest -q` från `gateway/`.

**Fas B (MEX-023) — inställningar, minne, per-user-lösenord:**

11. `cli.py hash-password` — generera bcrypt-hash. Manuellt test: kör CLI, klistra
    in hash i `acl.yaml`, verifiera inloggning via `login-app`.
12. `login-app/app.py` — per-user-hash + fallback. `pytest tests/test_login.py`.
13. `web/api/accounts.py` — `api_accounts_list/link/unlink`. Enhetstester med
    mockad `account.py`.
14. `web/api/accounts.py` — kalenderläge get/set. Testa med mockad `calendar.py`.
15. `web/pages/settings.html` + `web/static/settings.js` — flikar, kontorad,
    statusdot, poll-flöde, kalenderläge-select, profil-rendering.
    `pytest tests/test_settings_routes.py`. Manuellt: koppla Google i nytt fönster,
    se statusdot uppdateras utan sidladdning.
16. `web/api/memory.py` — alla fem endpoints. `pytest tests/test_memory_api.py`.
17. `web/pages/memory.html` + `web/static/memory.js` — filträd, visare, sök,
    historik-drawer, återställ-bekräftelse.
    Manuellt: revert en fil, se att vault-git har nytt commit.
18. Integrationstester — `pytest tests/test_web_integration.py` täcker
    inloggning → settings → koppla → poll → länkad.
19. CI grön — full svit + docs-index.

---

## 7. Utvecklingsinstruktioner / Kodkontrakt

### Konventioner

- SPDX-huvud på alla `.py`-filer: `# SPDX-License-Identifier: AGPL-3.0-or-later`
- Python: `from __future__ import annotations`, typ-annoteringar, ingen global
  mutable state utöver cache-mönster (`_HTML_CACHE: dict[str,str] = {}`).
- HTML: `innerHTML` används aldrig med icke-kontrollerat innehåll. DOM byggs via
  `createElement + textContent`. Markdown renderas av `mdView()` (DOM-noder,
  inte `innerHTML`).
- JS: inga externa beroenden. ES2022. `async/await`, `??`, optional chaining.
  Inte `var`. Inte `eval`.
- CSS: bara custom properties och klassnamn. Inga CSS-ramverk.
- Alla webb-API-routes ska ha ett enhetstester som mockar tool-funktionen och
  verifierar rollkontroll (reader, collaborator, owner, ej-autentiserad).

### Invariant: webb-UI är ett tunt HTTP-lager

Varje `/app/api/*`-endpoint ska vara ≤20 rader kod. Allt utöver HTTP-parsing,
rollkontroll och JSON-serialisering hör hemma i tool-funktionerna. Om du hittar
dig själv skriva business-logik i `web/api/*.py` — flytta den till `tools/`.

### `_require_user(request)` — kontrakt

```python
def _require_user(request: Request) -> str:
    """Hämta autentiserad användare från session-cookie.
    Kastar HTTPException(401) om ej autentiserad.
    """
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="not_authenticated")
    return user
```

### `memory_revert` — kontrakt

```python
def memory_revert(acl: Acl, user_id: str, project: str, file: str, sha: str) -> dict:
    """
    Återställ {file} i {project}:s vault till commit {sha}.
    Kräver owner-roll (enforce:ad av anroparen).
    Kör: git checkout {sha} -- {safe_path}
         git commit -m "Revert {file} till {sha[:7]} (via webb-UI, {user_id})"
    Returnerar {new_sha: str} eller kastar ValueError vid ogiltig sha/path.
    Loggar via AuditLog(tool='memory_revert', user=user_id, project=project, ok=True).
    """
```

`safe_path`-validering: `file` får inte innehålla `..`, absoluta sökvägar eller
ligga utanför vault-roten. Returnera 400 om valideringen misslyckas.

### `account_link` — förväntat svar

`account_link(acl, user, "google")` returnerar `{"url": "https://..."}` (OAuth-URL).
`web/api/accounts.py` vidarebefordrar URL:en som `{"url": ...}` till JS som
öppnar den i nytt fönster. Ingen redirect på server-sidan.

### Filstruktur (Fas A + B)

```
gateway/src/memaix_gateway/
├── board/                      (oförändrat)
│   ├── board.html
│   └── routes.py
├── cli.py                      (NYTT — hash-password m.m.)
├── web/                        (NYTT)
│   ├── __init__.py
│   ├── routes.py               (shell-routes + /app/api/me)
│   ├── api/
│   │   ├── __init__.py
│   │   ├── accounts.py         (Fas B)
│   │   └── memory.py           (Fas B)
│   ├── pages/
│   │   ├── shell.html
│   │   ├── home.html
│   │   ├── board.html          (tunn board-wrapper)
│   │   ├── settings.html       (Fas B)
│   │   └── memory.html         (Fas B)
│   └── static/
│       ├── app.css
│       ├── app.js
│       ├── shell.js
│       ├── home.js
│       ├── settings.js         (Fas B)
│       └── memory.js           (Fas B)
└── login-app/
    └── app.py                  (per-user-hash, Fas B)
```

---

## 8. Acceptanskriterier

**Fas A:**

- [ ] `GET /board` returnerar HTTP 301 `Location: /app/board`. Befintliga bokmärken fungerar.
- [ ] `GET /app` returnerar HTML 200 med mörkt tema (`--bg:#0f1117` synlig i DevTools).
- [ ] `GET /app/api/me` returnerar korrekt JSON för autentiserad användare; 401 för ej autentiserad.
- [ ] Sidebar kollapsar/expanderar; tillstånd persisterar via localStorage.
- [ ] Projektväljare sätter `?project=X` i URL och synkar med localStorage.
- [ ] Board-drag är aktiverat för owner, inaktiverat (med tooltip) för reader/collaborator.
- [ ] Hem-sidan visar projektkort, aktivitetsfeed och att-göra-poster.
- [ ] Admin-länk i sidebar syns enbart för `is_admin = true`.
- [ ] `python -m pytest -q` från `gateway/` är grönt, inga regressions.

**Fas B:**

- [ ] `python -m memaix_gateway.cli hash-password` genererar bcrypt-hash som kan klistras in i `acl.yaml`.
- [ ] Inloggning med per-user-lösenord fungerar; fallback till delat lösenord om `password_hash` saknas.
- [ ] Flik Konton: alla tre statusdotar (linked/needs_relink/not_linked) visas korrekt.
- [ ] "Koppla Google" → nytt fönster öppnas, poll startar, statusdot uppdateras utan sidladdning.
- [ ] Kalenderläge-select sparar valt läge; reload visar det sparade värdet.
- [ ] Flik Profil: `om-{user}.md` renderas, onboarding-chip visar rätt status.
- [ ] Minnesutforskaren visar filträd, renderar markdown, söker och highlightar träffar.
- [ ] Historik-drawer visar commits med relativ tid; "Återställ hit" kräver bekräftelse.
- [ ] Återställning skapar nytt git-commit i vaulten, toast visar nytt SHA.
- [ ] `memory_revert` med `..` i filnamnet returnerar 400 (path-traversal-skydd).
- [ ] Full testsvit och docs-index grön.
