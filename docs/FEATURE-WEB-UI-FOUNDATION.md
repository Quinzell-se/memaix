# Funktion #22 — Webb-UI Fundament (Fas A)

SPDX-License-Identifier: AGPL-3.0-or-later

Designdok + byggspec för grundlagret i Memaix webb-UI: mörkt CSS-tema, delade
JS-verktyg, app-shell med sidebar/topbar, global projektväljare, mobilanpassad
layout och en startsidas-dashboard. Fas A levererar ett komplett navigerbart skal
som board-komponenten (och senare Fas B–D) kan monteras i, utan att bryta
befintlig `/board`-vy.

Byggs stegvis enligt [Byggordning](#5-byggordning) och
[Utvecklingsinstruktioner](#6-utvecklingsinstruktioner--kodkontrakt). Varje
steg ska vara självständigt grönt innan nästa påbörjas.

---

## 1. Vad användaren upplever

Användaren öppnar `https://memaix.example.com/app` och möts direkt av en mörk
applikation — samma mörka palett som login-sidan, inte det ljusa `/board`-temat.
Till vänster en sidebar på 220 px med logotyp, navigeringslänkar och en
projektväljare längst ner. Sidebaren kollapsar till 56 px ikoner via en
toggle-knapp (tillståndet sparas i `localStorage`).

Startsidan visar tre sektioner sida vid sida: **Att göra** (sammanfattning av
väntande utkorgsärenden, konton som behöver återkopplas, saknat
onboarding-underlag), **Mina projekt** (rutnät med projektkort — projektets
namn, användarens roll och ett ungefärligt antal kort i backloggen) och **Aktivitet**
(de senaste 20 audit-händelserna för de projekt användaren kan se).

Board nås via `GET /app/board` och renderas inuti skalet — utan omladdning av
sidbar eller topbar — identiskt med nuläget fast i mörkt tema och med korrekt
rollmedvetet drag. Gamla URL:en `/board` returnerar 301 till `/app/board` så att
bokmärken fungerar.

På mobil (< 900 px) ersätts sidebaren av en topbar med logotyp och
projektväljare samt en tab-bar längst ner (Hem · Board · Utk · Minne). Admin-
och inställningslänkar finns i user-menyn i topbaren.

---

## 2. Nyckelbeslut

1. **Ingen SPA-ram.** Varje vy är en server-renderad HTML-sida. JS är vanilla
   (ES2022 class + fetch). Inga build-steg, inga bundlers. Exakt samma approach
   som befintlig `board.html` — bara generaliserad och utdragen.

2. **Gemensam `_html_with_locale(page)`-fabrik.** Befintlig `_board_html_with_locale`
   generaliseras till `_html_with_locale(page: str, locale: str) -> str` som läser
   `web/pages/{page}.html`, injicerar i18n-strängar via `<!--MEMAIX_I18N-->` och
   lägger till CSRF-token. Alla vyer använder samma mönster.

3. **`web/`-katalog parallellt med `board/`.** Inga renames av `board/`-paketet
   för att inte skada git-historik och befintliga importer. `web/` är ett nytt
   Starlette-routepaket bredvid `board/`. `/board`-routerna lever kvar som 301
   redirect.

4. **`GET /app/api/me` är kärnan.** Allt roll- och projektberoende JavaScript
   hämtar sin grund från ett enda anrop — returnerar `{user, is_admin, role_map,
   projects, needs_relink, pending_outbox}`. Inget JS-lager gissar roller.

5. **Global projektväljare lever i `localStorage.memaix_project`.** URL-param
   `?project=X` har alltid företräde och skriver över localStorage. Projektpickern
   är en `<select>` med tillhörande rollvisning — inget komplicerat UI-beroende.

6. **Cookie-autentisering hanteras i `web/routes.py`**, inte i app.js. 401 från
   `/app/api/*` triggar `window.location = '/login?next=' + encodeURIComponent(location.pathname)`.
   Login-appen (Hydra/OAuth) påverkas inte.

   > **Reconciliation 2026-07:** `_require_user` återanvänder board:ens redan
   > befintliga signerade cookie (`board/routes.py::_check_cookie` — HMAC-signerad
   > med `HYDRA_SYSTEM_SECRET`, fail-closed). Ingen `SessionMiddleware` och ingen
   > server-side session store införs — cookien är stateless och delas med `/board`.
   > `/app/*` och `/board` är samma session. Full kontraktsdefinition i
   > FEATURE-WEB-UI-MVP.md (§`_require_user`).

7. **Board-logiken i `board/routes.py` berörs minimalt.** Boards API-routes
   (`/board/api/*`) behålls orörda. Enda förändringen: `/board`-sidroute returnerar
   301 istället för `board.html`. Board-UI:t `board.html` wrappas in i
   app-shellets `<main>`-slot via en iframe eller inline-include — se Komponent 3.

8. **Mörkt tema är CSS custom properties, inte klasser.** `:root` sätter samtliga
   design tokens. Dark-only i v1 — ingen light-toggle. Tematoken-värdena matchar
   login-appen exakt (se §4.1).

---

## 3. Översikt

```
Browser                       Gateway (Starlette)
──────                        ──────────────────
GET /app          ──────────► web/routes.py
                              _html_with_locale("home")
                  ◄──────────  <html> med shell + home-slots

GET /app/board    ──────────► _html_with_locale("board")
                              (board.html inbäddat i shell)

GET /board        ──────────► 301 → /app/board

GET /app/static/* ──────────► FileResponse(web/static/*)

GET /app/api/me   ──────────► web/api/me.py
                              _require_user → Acl → TokenStore
                  ◄──────────  {user, is_admin, role_map, projects,
                                needs_relink, pending_outbox}

GET /board/api/*  ──────────► board/routes.py  (oförändrat)

Klient-JS
──────────
app.js: api(), toast(), modal(), mdView(), t()
home.js: hämtar /api/me + /board/api/activity → renderar dashboard
shell.js: sidebar-toggle, projektpicker localStorage-sync, poll-badges
```

---

## 4. Komponenter

### 4.1 `web/static/app.css` — Mörkt tema + baskomponenter

Enda CSS-filen som laddas globalt. Definierar design tokens, reset, typografi och
återanvändbara klasser.

```css
/* Design tokens — identiska med login-appen */
:root {
  --bg:           #0f1117;
  --surface:      #1a1d27;
  --surface-2:    #222637;   /* för hover-tillstånd */
  --border:       #2d3044;
  --text:         #e2e8f0;
  --muted:        #94a3b8;
  --primary:      #6366f1;
  --primary-light: rgba(99,102,241,.15);
  --danger:       #ef4444;
  --success:      #38a169;
  --warning:      #f59e0b;
  --card-shadow:  0 1px 3px rgba(0,0,0,.5);

  /* Layout */
  --sidebar-w:    220px;
  --sidebar-collapsed: 56px;
  --topbar-h:     56px;
  --tab-h:        56px;

  /* Typsnitt */
  --font:         system-ui, -apple-system, 'Segoe UI', sans-serif;
  --mono:         'JetBrains Mono', 'Fira Mono', ui-monospace, monospace;
  --text-sm:      0.875rem;
  --text-xs:      0.75rem;
}
```

Klasser som ska finnas: `.btn`, `.btn-primary`, `.btn-danger`, `.badge`,
`.badge-warning`, `.badge-success`, `.card`, `.surface`, `.muted`, `.mono`,
`.toast-container`, `.modal-backdrop`, `.modal-box`, `.tabs`, `.tab-active`,
`.empty-state`, `.spinner`.

### 4.2 `web/static/app.js` — Delade JS-verktyg

Vanlig ES2022 utan importmap eller bundler — läses med `<script src="/app/static/app.js">`.

**`api(method, path, body = null) → Promise<any>`**

```js
async function api(method, path, body = null) {
  const opts = { method, headers: { 'Content-Type': 'application/json' },
                 credentials: 'same-origin' };
  if (body !== null) opts.body = JSON.stringify(body);
  const res = await fetch(path, opts);
  if (res.status === 401) {
    window.location = '/login?next=' + encodeURIComponent(location.pathname);
    return;
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error || res.statusText);
  }
  return res.json();
}
```

**`toast(msg, type = 'info')`** — skapar ett `<div class="toast toast-{type}">`,
lägger det i `.toast-container`, tar bort det efter 4 s. `type` ∈ `info | success
| warning | error`.

**`modal(html) → { close() }`** — skapar `.modal-backdrop` + `.modal-box`, sätter
`innerHTML = html` (safe: html byggs med DOM-metoder, inte användardata direkt),
returnerar handle med `close()`-metod. Stängs med Escape, klick utanför eller
`close()`. Returnerar ett Promise-liknande handle, inte ett Promise, för att
undvika implicit await-mönster.

**`mdView(el, markdown)`** — enkel markdown-rendering utan extern bibliotek.
Stöder: rubriker (# ## ###), fetstil (**text**), kursiv (*text*), kodsnuttar
(backtick), kodblock (tre backticks), listor (- / * / 1.), horisontell linje
(---), radbrytning (dubbelt newline = `<p>`). Läser in DOM-noder med
`textContent` — aldrig direkt innerHTML från markdown. Implementation via
regex-to-DOM-node-steg (inte eval, inte innerHTML av markdown).

**`t(key) → string`** — slår upp `window.I18N[key]`; returnerar `key` om den
saknas (synlig i UI som fallback).

**`pollBadge(path, badgeEl, interval = 10_000)`** — pollar `path` med `api()`,
uppdaterar `badgeEl.textContent` och `badgeEl.hidden`. Pausar när
`document.visibilityState === 'hidden'` (Page Visibility API). Returnerar `{ stop() }`.

### 4.3 App-shell `web/pages/shell.html` (gemensam layout)

Alla sidor inkluderar `shell.html` som basmall. Implementeras som ett HTML-fragment
med `<!--MEMAIX_CONTENT-->` som ersätts i `_html_with_locale()` med sidans
specifika markup.

```
┌─────────────────────────────────────────────────────────┐
│ sidebar (220px, border-right)     │ main                 │
│  ┌──────────────────────────────┐ │  ┌─────────────────┐│
│  │ ⬡ memaix      [collapse ▸]  │ │  │ topbar (56px)   ││
│  │ ──────────────────────────── │ │  │ [bread] [search] ││
│  │ 🏠 Hem                       │ │  │ [proj ▾] [user]  ││
│  │ 📋 Board                     │ │  └─────────────────┘│
│  │ 📤 Utkorg         (3)        │ │                      │
│  │ 🧠 Minne                     │ │  <content>           │
│  │ ──────────────────────────── │ │                      │
│  │ ⚙️ Inställningar             │ │                      │
│  │ 🛡 Admin          (admin)    │ │                      │
│  │ ──────────────────────────── │ │                      │
│  │ [acme ▾]  (projektväljare)   │ │                      │
│  │ alice · owner                │ │                      │
│  │ [Logga ut]                   │ │                      │
│  └──────────────────────────────┘ │                      │
└─────────────────────────────────────────────────────────┘
```

Sidebaren döljer textetiketter och visar bara ikoner (56 px bred) när
`data-collapsed="true"` är satt på `<body>`. `localStorage.memaix_sidebar_collapsed`
persisterar tillståndet.

Admin-länken renderas med `hidden`-attribut som tas bort av `shell.js` om
`me.is_admin === true`. Utkorg-badge uppdateras av `pollBadge('/app/api/me', ...)`.

**Mobil (< 900 px, CSS `@media`):**

```
┌──────────────────────────────────┐
│ topbar: [⬡] [acme ▾]  [user ☰]  │  ← 56px
├──────────────────────────────────┤
│                                  │
│         <content>                │
│                                  │
├──────────────────────────────────┤
│ [🏠 Hem] [📋 Board] [📤] [🧠]   │  ← 56px tab-bar
└──────────────────────────────────┘
```

Sidebar visas inte på mobil. Tab-bar har fyra flikar med ikoner och etiketter.
Aktiv flik är markerad med `--primary`-färg.

### 4.4 `web/static/shell.js` — Shell-beteende

Laddas sist på varje sida. Hanterar:

- Sidebar-toggle: klick på collapse-knapp → toggle `data-collapsed` på `<body>` +
  skriv `localStorage.memaix_sidebar_collapsed`.
- Projektpicker: `<select id="project-picker">`, fyller alternativ från `me.projects`,
  sätter valt värde från URL-param `?project=X` eller `localStorage.memaix_project`.
  Vid ändring: uppdaterar `localStorage.memaix_project`, navigerar till
  `location.pathname + '?project=' + encodeURIComponent(val)`.
- User-badge: skriver `me.user + ' · ' + (role_map[project] ?? 'admin')` i
  `#user-badge`-elementet.
- Admin-länk: `document.querySelector('.nav-admin').hidden = !me.is_admin`.
- Utkorg-badge: `pollBadge('/app/api/me', document.querySelector('.outbox-badge'))`.

### 4.5 `web/pages/home.html` + `web/static/home.js` — Startsida `/app`

**Att göra-kortet** — `<div class="card todo-card">`:

Hämtar `me.pending_outbox`, `me.needs_relink`, `me.onboarding_missing` och
renderar en lista med prioritetsordnade åtgärder. Tomma sektioner visas inte.
Klick på "Gå till utkorgen" navigerar till `/app/outbox`. Klick på "Koppla konto"
öppnar `/app/settings#accounts`.

**Projektkortrutnät** — `<div class="projects-grid">`:

Loopar `me.projects` och renderar ett `.card.project-card` per projekt med:
- Projektnamn (H3)
- Roll-chip (`owner` = `--primary`, `collaborator` = `--muted`, `reader` = `--muted`)
- Kortantal (från `/board/api/board?project=X` — hämtas lazy, renderas med en
  `<span class="spinner">` tills svar kommit)
- Länk "Öppna board →"

**Aktivitetsfeed** — `<div class="activity-feed">`:

Hämtar `GET /board/api/activity` (utan projektfilter, returnerar de senaste 20
händelserna för alla projekt användaren ser). Varje rad:

```
[✓|✗] <tool>  ·  <project>  ·  <relativ tid>
      <detail-text om ej tom, i .mono>
```

Grön bock för `ok=true`, röd kryss för `ok=false`. Relativ tid: "just nu",
"2 m", "3 h", "igår", datumformat för äldre. Feeden laddas en gång vid
sidladdning — ingen poll i v1 (refresh ger nytt uttag).

### 4.6 `web/routes.py` — Backend-routes för `/app`

```python
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Web-UI app-shell routes — /app och statiska tillgångar."""

_WEB_DIR  = Path(__file__).parent
_PAGES    = _WEB_DIR / "pages"
_STATIC   = _WEB_DIR / "static"
_HTML_CACHE: dict[str, str] = {}


def _html_with_locale(page: str, locale: str) -> str:
    """Läs pages/{page}.html, injicera i18n och returnera färdig HTML."""
    ...

async def app_index(request: Request) -> HTMLResponse: ...
async def app_page(request: Request) -> HTMLResponse: ...   # /app/{page}
async def app_static(request: Request) -> Response: ...     # /app/static/{path}
async def board_redirect(request: Request) -> Response: ... # 301 /board → /app/board
async def api_me(request: Request) -> JSONResponse: ...     # GET /app/api/me
```

`api_me` returnerar:

```json
{
  "user":            "alice",
  "is_admin":        false,
  "role_map":        {"acme": "owner", "project-a": "collaborator"},
  "projects":        ["acme", "project-a"],
  "needs_relink":    ["google"],
  "pending_outbox":  0,
  "onboarding_missing": false
}
```

`needs_relink` hämtas från `TokenStore` (om `MEMAIX_TOKEN_DB` är satt) — tom
lista om token-DB ej konfigurerad. `pending_outbox` är `0` i Fas A (utkorg
byggs i Fas C); fältet är med för att JS-koden inte ska behöva ändras.

Route-tabell (läggs till i `__main__.py` bredvid `board_routes`):

```python
from .web.routes import web_routes

app = Starlette(routes=[*board_routes, *web_routes])
```

```python
web_routes = [
    Route("/app",                app_index,    methods=["GET"]),
    Route("/app/{page:str}",     app_page,     methods=["GET"]),
    Route("/app/static/{path:path}", app_static, methods=["GET"]),
    Route("/app/api/me",         api_me,       methods=["GET"]),
    Route("/board",              board_redirect, methods=["GET"]),
]
```

---

## 5. Byggordning

Bygg och verifiera i denna ordning. Varje steg är självständigt testbart.

1. **`web/static/app.css`** — Definiera alla design tokens + reset + bas-klasser.
   Verifiera manuellt i browser: ladda `/app/static/app.css`, bekräfta att variabler
   finns i DevTools.

2. **`web/static/app.js`** — `api()`, `toast()`, `modal()`, `mdView()`, `t()`,
   `pollBadge()`. Enhetstester i `tests/test_web_js.py` via `subprocess` + `node`
   (eller alternativt manuell verifiering i browser-konsolen).

3. **`web/routes.py`** — `_html_with_locale()`, `app_static`, `board_redirect`
   (301). Kör `pytest tests/test_web_routes.py` — bekräfta att 301 fungerar.

4. **`web/pages/shell.html`** + **`web/static/shell.js`** — Skelett utan innehåll.
   Ladda `/app` i browser, bekräfta sidebar + topbar syns med rätt mörkt tema.

5. **`GET /app/api/me`** i `web/routes.py` — autentisering, Acl, TokenStore-integrering.
   `pytest tests/test_api_me.py`.

6. **Sidebar-beteende** i `shell.js` — toggle, localStorage, projektpicker, user-badge,
   admin-länk. Manuell verifiering med en testanvändare.

7. **`web/pages/home.html`** + **`web/static/home.js`** — Att-göra-kort, projektkortrutnät,
   aktivitetsfeed. `pytest tests/test_web_home.py` (mock `api_me` + `api_activity`).

8. **Board-integration** — `web/pages/board.html` är en tunn wrapper som lägger
   `board.html`-innehållet inuti shell-`<main>`. Verifiera att drag-och-släpp,
   sprint-filter och aktivitetspanel fungerar som tidigare.

9. **Mobil-layout** — `@media`-regler i `app.css`, tab-bar i `shell.html`. Testa
   med DevTools mobile emulation (375 px, 768 px).

10. **CI** — Lägg till test-steg i `.github/workflows/` (om CI finns) eller
    bekräfta att `python -m pytest -q` från `gateway/` är grönt.

---

## 6. Utvecklingsinstruktioner / Kodkontrakt

Konventioner (matcha befintlig kod):

- SPDX-huvud på alla `.py`-filer: `# SPDX-License-Identifier: AGPL-3.0-or-later`
- Python: typ-annoteringar, `from __future__ import annotations`, inga globala
  mutable defaults utöver de befintliga cache-mönstren (`_HTML_CACHE: dict[str,str] = {}`).
- HTML: serveras som UTF-8. Ingen `innerHTML` med icke-kontrollerat innehåll.
  Bygga DOM via `createElement + textContent`, inte stränginterpolation.
- JS: inga externa beroenden. ES2022 (`class`, `async/await`, optional chaining,
  `??`). Inte `var`.
- CSS: bara custom properties och klassnamn. Inga CSS-ramverk.

### Filstruktur

```
gateway/src/memaix_gateway/
├── board/                         (oförändrat)
│   ├── board.html
│   └── routes.py
└── web/                           (nytt)
    ├── __init__.py
    ├── routes.py
    ├── pages/
    │   ├── shell.html             (basmall + shell-markup)
    │   ├── home.html              (<!--MEMAIX_CONTENT-->-slot för Hem)
    │   └── board.html             (tunn wrapper → board/board.html-innehåll)
    └── static/
        ├── app.css
        ├── app.js
        ├── shell.js
        └── home.js
```

### `_html_with_locale(page, locale)` — kontrakt

```python
def _html_with_locale(page: str, locale: str) -> str:
    """
    Läser web/pages/{page}.html (cached), injicerar i18n-strängar via
    <!--MEMAIX_I18N-->, returnerar färdig HTML-sträng.
    Kastar FileNotFoundError om sidan saknas (→ 404 i route-handleren).
    """
```

Cache: `_HTML_CACHE[page]` lagrar rå HTML; i18n-injektion sker varje anrop
(strängar kan ändras vid restart). I dev-läge (`MEMAIX_DEV=1`): läs från disk
varje gång (ingen cache).

### `api_me` — kontrakt

```python
async def api_me(request: Request) -> JSONResponse:
    """
    GET /app/api/me — returnerar användarinfo + roller + projektstatus.
    401 om ej autentiserad.
    Hämtar: _get_acl(), visible_projects(), is_admin(), grants().
    Hämtar needs_relink från TokenStore om MEMAIX_TOKEN_DB är satt.
    pending_outbox alltid 0 i Fas A.
    """
```

> **Reconciliation 2026-07 — Acl-konvention (gäller ALLA `/app`-routes i alla
> faser):** Specarna skriver ofta `Acl.from_config()` utan argument, men den
> faktiska signaturen är `Acl.from_config(cfg: dict)` och tar acl-underträdet
> (`config.load()["acl"]`). Använd i stället `server._get_acl()` i webb-routes —
> den bygger och **cachar** Acl och kan tömmas via `server.reload_acl()` (som
> admin-skrivvägen i Fas D behöver). Läs alltså `_get_acl()` där specarnas
> kod-exempel säger `Acl.from_config()`.

### `board_redirect` — kontrakt

```python
async def board_redirect(request: Request) -> Response:
    """GET /board → 301 /app/board (bevarar query-params)."""
    qs = request.url.query
    target = "/app/board" + (f"?{qs}" if qs else "")
    return Response(status_code=301, headers={"Location": target})
```

### Acceptanskriterier

- [ ] `GET /board` returnerar HTTP 301 med `Location: /app/board`. Gamla bokmärken
      fungerar.
- [ ] `GET /app` returnerar HTML 200 med mörkt tema (`--bg:#0f1117` synlig i CSS).
- [ ] `GET /app/static/app.css` returnerar CSS-fil med alla design-tokens.
- [ ] `GET /app/api/me` returnerar korrekt JSON för autentiserad användare;
      returnerar 401 för ej autentiserad.
- [ ] Sidebar kollapsar till 56 px och återställs vid nästa sidladdning
      (localStorage).
- [ ] Projektväljare sätter `?project=X` i URL och skriver `localStorage.memaix_project`.
- [ ] Hem-sidan visar projektkort, aktivitetsfeed och (om tillämpligt) att-göra-poster.
- [ ] Board fungerar via `/app/board` i mörkt tema; drag-och-släpp kräver
      owner-roll (oförändrat beteende).
- [ ] Admin-länk i sidebar syns enbart för `is_admin = true`.
- [ ] Outbox-badge i sidebar uppdateras av `pollBadge`; pausa när tab är dold.
- [ ] Mobilvy (375 px): sidebar dold, tab-bar synlig längst ner, topbar med
      projektväljare.
- [ ] `python -m pytest -q` från `gateway/` är grönt; inga regressions i befintliga
      board-tester.

---

## Framtida arbete (Fas B–D)

- **Fas B** — Inställningar/Konton (OAuth-länkflöde), Profil (onboarding-vy),
  Minnesutforskaren, per-user-lösenord i `acl.yaml`.
- **Fas C** — Utkorgs-UI med godkänn/avvisa-modaler, kortmodal med kommentar +
  V/C/R-poäng, admin läsvyer.
- **Fas D** — Global sökning (funktion #2), brief-inställningar (funktion #1),
  admin skrivoperationer + kill-switch + MFA, ångra-tidslinje (funktion #5).
  Se `FEATURE-WEB-UI-PHASE2.md`.
