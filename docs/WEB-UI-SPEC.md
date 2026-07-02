# Memaix Web-UI — UI/UX-spec + byggspec

**Underlag:** kodgenomgång av `gateway/src/memaix_gateway/` (server.py, board/, tools/, acl.py), `login-app/`, `config/*.example.yaml`, docs (ARCHITECTURE, MCP-API, SAFETY, PER-USER-OAUTH, ROADMAP, FEATURE-APPROVAL-OUTBOX, FEATURE-PROACTIVE-BRIEF, FEATURE-SEMANTIC-SEARCH).

**Verkligheten i koden idag (viktigt för allt nedan):**
- Roller i `acl.py` är `reader < collaborator < owner` — **det finns ingen admin-roll i koden.** Den måste införas (se §1.4).
- Board-auth är cookie + **ett delat lösenord** för alla i `MEMAIX_ALLOWED_USERS` (`MEMAIX_LOGIN_PASSWORD_HASH`, en hash för alla). Det håller inte för ett fleranvändar-UI (se §7.2).
- Board-flytt (PATCH) kräver `owner` — collaborator kan alltså **inte** flytta kort idag, trots att `backlog_comment`/`backlog_score` är collaborator-verktyg.
- Befintligt `board.html` är **ljust** tema; login-appen och OAuth-callback-sidan är **mörka** (#0f1117-paletten). Mörkt tema = samordna board med login-appens palett.
- i18n: JSON-strängar injiceras server-side via `<!--MEMAIX_I18N-->`.
- Utkorg, brief, semantisk sökning är **specade men inte byggda** — UI:t ska ha reserverad plats för dem.

---

## 1. Rollanalys

### 1.1 Användare (reader/collaborator)
Se sina projekt och board, läsa kort (reader) + kommentera/poängsätta kort (collaborator), se aktivitet i sina projekt, koppla sina egna OAuth-konton, välja kalenderläge, se sin onboarding-profil.

### 1.2 Ägare (owner, per projekt)
Allt ovan plus: flytta kort, planera sprintar, godkänna/avvisa utkorgsärenden, se projektets konfiguration, se projektets fulla aktivitet/audit, se RAID-logg och sprint-burndown. **Obs:** owner är per projekt — UI:t måste vara rollmedvetet per valt projekt.

### 1.3 Admin (systemadmin)
Allt ovan för alla projekt plus: användarlista med grants, kill-switch, global audit-logg, systemhälsa (doctor, circuit breakers), instanskonfig, vault-översikt.

### 1.4 Hur admin införs
```yaml
users:
  alice:
    admin: true          # NYTT — systemadmin
    oauth_subjects: [alice]
    grants: { acme: owner, ... }
```
Plus `Acl.is_admin(user_id)` och att `visible_projects()` för admin returnerar alla projekt. MVP: visa varningsbanner "MFA ej aktiverat" tills MFA finns (SAFETY §9).

### 1.5 Rollmatris

| UI-element | reader | collaborator | owner | admin |
|---|---|---|---|---|
| Board: se kort | ✅ | ✅ | ✅ | ✅ |
| Board: dra kort | ❌ | ❌ | ✅ | ✅ |
| Kort: kommentera/poäng | ❌ | ✅ | ✅ | ✅ |
| Utkorg: godkänn | ❌ | ❌ | ✅ | ✅ |
| Konton: koppla egna | ✅ | ✅ | ✅ | ✅ |
| Projektinställningar | ❌ | ❌ | ✅ läs | ✅ |
| Admin-sektion | ❌ | ❌ | ❌ | ✅ |

Princip: **dölj inte bara — inaktivera med förklaring** (t.ex. drag-handtag med tooltip "Kräver owner-roll"), men dölj hela admin-sektionen helt för icke-admin.

---

## 2. Informationsarkitektur

### 2.1 Sidkarta

```
/login, /consent            (Hydra — oförändrade)
/link/{provider}[/callback] (oförändrade; callback-sidan får "Tillbaka"-länk till /app/settings)

/app                        App-shell + Hem (dashboard)
├── /app/board              Kanban (ersätter /board; /board → 301)
│     ?project=X&sprint=Y
│     └── modal: kortdetalj (+ kommentar/poäng för collaborator+)
├── /app/outbox             Utkorg (byggs med feature #3; dold i nav tills dess)
│     └── modal: ärende-preview + Godkänn/Avvisa
├── /app/memory             Minnesutforskare
│     ├── lista noter per projekt + sök
│     └── drawer: git-historik + revert-bekräftelse
├── /app/settings           Mina inställningar
│     ├── flik: Konton      (länkade OAuth-konton, kalenderläge)
│     ├── flik: Profil      (onboarding-profil, status)
│     └── flik: Brief       (fas 3 — schema/kanaler)
└── /app/admin              Endast admin
      ├── flik: Användare   (grants-matris, kill-switch fas 3)
      ├── flik: Projekt     (resurser, allow_send, outbox-läge)
      ├── flik: Audit       (global logg med filter)
      └── flik: System      (hälsa, doctor, version, locale)
```

### 2.2 Modaler/drawers
- **Kortmodal** — metadata + kommentarslista + poängredigering (V/C/R-steppers); deep-link `?item=BL-123`
- **Utkorgsmodal** — full preview; Godkänn / Avvisa med orsak
- **Historik-drawer** (minne) — commits med relativ tid; "Återställ hit" → bekräftelsedialog
- **Bekräftelsedialog** — generisk; destruktiva åtgärder kräver extra klick (SAFETY §8)
- **Länka konto** — öppnar `/link/{provider}` i nytt fönster; settings-sidan pollar `account_list` var 3 s

### 2.3 Nyckeldataflöden

**Koppla Google-konto:**
Settings → "Koppla Google" → `GET /app/api/accounts/link/google` → `window.open(link_url)` → befintlig `/link/google` → callback-HTML → settings pollar `GET /app/api/accounts` var 3 s i 2 min → rad dyker upp med status `linked`.

**Godkänna utgående mejl:**
Badge på Utkorg i nav (poll var 10 s) → `/app/outbox` → preview-modal → "Godkänn" → `POST /app/api/outbox/{id}` → optimistisk flytt. Konflikt → toast "Redan avgjort av {user}".

---

## 3. Navigationsstruktur

### Desktop (≥900px): vänster sidebar, 220px, kollapsbar till 56px
```
⬡ memaix
──────────
🏠 Hem
📋 Board
📤 Utkorg      (3)    ← badge; dold tills feature #3
🧠 Minne
──────────
⚙️ Inställningar
🛡  Admin              ← endast is_admin
──────────
[projektväljare]      ← global, styr Board/Minne/Utkorg
alice · owner         ← user-badge + roll i valt projekt
Logga ut
```

### Mobil (<900px): topbar + bottom-tabs
- Topbar: logga, projektväljare (kompakt dropdown), user-menu
- Bottom-tab-bar: Hem · Board · Utkorg · Minne (Admin via user-menyn)
- Board på mobil: horisontell snap-scroll, en kolumn i taget; drag → "Flytta till…"-åtgärd i modal

---

## 4. Sida-för-sida-spec

### 4.1 `/app` — Hem
**Syfte:** landningspunkt; "vad händer, vad väntar på mig".
**API:** `GET /app/api/me`, `GET /board/api/activity`, `GET /app/api/outbox?status=pending` (fas C).

```
┌──────────────────────────────────────────────────────┐
│ God morgon, alice                       [datum]      │
├─────────────────────┬────────────────────────────────┤
│ Att göra             │ Aktivitet (senaste 50)         │
│ 📤 3 i utkorgen     │ ✓ alice · board_move · 2m     │
│ 🔗 Google needs_relink│   acme  BL-14: inbox→triaged │
│ 👤 Onboarding saknas│ ✗ bob · email_send · 1h       │
│                     │   project-a  rate_limited      │
│ Mina projekt         │                                │
│ [acme owner 12k]    │                                │
│ [project-a collab]  │                                │
└─────────────────────┴────────────────────────────────┘
```

### 4.2 `/app/board` — Kanban
**Förändringar mot idag:** mörkt tema i shell, rollmedvetet drag (`draggable` styrs av roll), URL-param-state, aktivitetspanel flyttas till Hem. Kortmodal utökas med kommentarer + V/C/R-steppers (collaborator+).

### 4.3 `/app/outbox` — Utkorg (fas C, med feature #3)
```
┌ Utkorg ──────── [Väntande | Avgjorda] [projekt ▾] ┐
│ ⏳ email_send · acme · förfaller om 68h             │
│    Till: kund@example.com — "Offert v2"             │
│    [Förhandsgranska]           [Avvisa] [Godkänn ✓] │
└─────────────────────────────────────────────────────┘
```
Status: pending=gul, executed=grön, rejected/expired=grå, failed=röd. Poll var 10 s.

### 4.4 `/app/memory` — Minnesutforskare
**API:** `GET /app/api/memory/notes|note|search|history`, `POST /app/api/memory/revert`.
```
┌ Minne · acme ──── [🔍 sök…] ┐
│ noter          │  decisions.md│
│ ▸ decisions.md │  # Beslut    │
│ ▸ about-bob.md │  - 2026-06…  │
│ ▸ kund-x/      │  [Historik]  │
└────────────────┴──────────────┘
```
MVP: ingen redigering i UI — skrivning är AI:ns jobb; UI är granskning/insyn.

### 4.5 `/app/settings` — Mina inställningar

**Flik Konton:**
```
┌ Konton ─────────────────────────────────────┐
│ Google   alice@gmail.com     ● linked        │
│                                 [Koppla ur] │
│ Microsoft —                  [Koppla ▸]     │
│ ──────────────────────────────────────────  │
│ Kalenderläge (acme):  ◉ OAuth  ○ iCal-URL  │
│                       ○ FreeBusy ○ Ingen    │
└─────────────────────────────────────────────┘
```
**Flik Profil:** renderar `shared/om-{user}.md`, status-chip, "uppdateras via AI-klienten".
**Flik Brief (fas D):** schema, tidszon, tysta timmar, kanaler.

### 4.6 `/app/admin` — Administration (is_admin, MVP = läsvy)
- **Användare:** matris users × projects med roll-chips; fas D: kill-switch
- **Projekt:** allow_send, outbox-läge, kortstatistik
- **Audit:** filter på user/projekt/verktyg/ok/tid; expanderbara felrader
- **System:** hälsa, version, oauth_providers (aldrig secrets), doctor-resultat

---

## 5. Komponentbibliotek

| Komponent | Finns? | Beskrivning |
|---|---|---|
| `app-shell` | Nytt | Sidebar + topbar + content-slot; badge-poll |
| `login-gate` | Restylas | Mörkt tema, återanvänd logik |
| `project-picker` | Utökas | Global, URL-param + localStorage |
| `kanban-column/card` | Finns | Rollmedvetet drag |
| `modal` | Generaliseras | Kortmodal + utkorgsmodal + bekräftelse |
| `confirm-dialog` | Nytt | Promise-baserad, destruktiv-knapp röd |
| `drawer` | Nytt | Historik-panel, mobilnav |
| `toast` | Finns | Behålls rakt av |
| `md-view` | Finns | Bryts ut till app.js |
| `activity-feed` | Finns | Bryts ut ur board.html |
| `data-table` | Nytt | Admin-audit, sorterbar, expanderbar |
| `empty-state` | Nytt | Ikon + text + CTA |
| `tabs` | Nytt | URL-hash-sync |
| `stepper` | Nytt | 1–5 för V/C/R-poäng |
| `account-row` | Nytt | Provider-ikon, status-punkt, åtgärdsknapp |
| `poll-badge` | Nytt | Nav-badge, pausar vid hidden tab |
| `api()` | Bryts ut | fetch-wrapper med 401-hantering |

---

## 6. Byggordning

### Fas A — Fundament
1. Mörkt tema + `app.css`/`app.js` (shared assets, api(), toast, modal, md-view, i18n)
2. App-shell + `/app`-Hem (projektkort, aktivitetsfeed, att-göra-kort)
3. Board → `/app/board` i mörkt tema i shell; `/board` → 301; rollmedvetet drag

### Fas B — MVP komplett
4. Settings/Konton — link-flöde från UI, unlink, kalenderläge, needs_relink
5. Settings/Profil (läsvy)
6. Minnesutforskaren (lista, läs, sök, historik, revert)
7. Per-user-lösenord (blockerare för multi-user)

**= MVP.** Hem + Board + Minne + Konton, mörkt, mobilanpassat.

### Fas C — I takt med features
8. Utkorg (byggs med FEATURE-APPROVAL-OUTBOX)
9. Kortmodal: kommentar + V/C/R-poäng
10. Admin läsvyer

### Fas D — Fas 2/3
11. Global sökning (feature #2 — sökfält i topbar)
12. Brief-inställningar (feature #1)
13. Admin skrivoperationer + kill-switch + MFA-krav
14. Ångra-tidslinje (FEATURE-UNDO-TIMELINE)

---

## 7. Teknisk byggspec

### 7.1 CSS-tema
```css
:root {
  --bg: #0f1117;
  --surface: #1a1d27;
  --border: #2d3044;
  --text: #e2e8f0;
  --muted: #94a3b8;
  --primary: #6366f1;
  --primary-light: rgba(99,102,241,.15);
  --danger: #ef4444;
  --success: #38a169;
  --warning: #f59e0b;
  --card-shadow: 0 1px 3px rgba(0,0,0,.5);
}
```

### 7.2 Arkitektur: utöka board-approachen — inte SPA
- Server-renderade statiska HTML-sidor per vy. Generalisera `_board_html_with_locale()` till `_html_with_locale(page)`.
- Katalog: döp om `board/` till `web/` (eller lägg `web/` bredvid): `web/pages/*.html`, `web/static/app.css|app.js`, `web/routes.py`, `web/api/`.
- Per-user-lösenord: `users.alice.password_hash: "salt:hex"` i acl.yaml + `_verify_password(user, provided)` i routes.py och login-app/app.py.

### 7.3 Nya routes

| Route | Metod | Roll | Implementation |
|---|---|---|---|
| `/app`, `/app/board`, `/app/memory`, `/app/settings`, `/app/admin`, `/app/outbox` | GET | HTML | `_html_with_locale(page)` |
| `/app/static/{path}` | GET | öppen | statisk fil |
| `/board` | GET | — | 301 → `/app/board` |
| `/app/api/me` | GET | cookie | user, roll-map, is_admin, onboarding-status, konton |
| `/app/api/accounts` | GET | cookie | `TokenStore.list_accounts(user)` |
| `/app/api/accounts/link/{provider}` | GET | cookie | `account_link` → `{link_url}` |
| `/app/api/accounts/{provider}/{account}` | DELETE | cookie | `account_unlink` |
| `/app/api/calendar-mode` | GET/POST | collaborator | bryt ut `calendar_setup`-kärnan ur server.py |
| `/app/api/memory/notes|note|search|history` | GET | reader | wrappers över tools/memory.py |
| `/app/api/memory/revert` | POST | collaborator | `memory_revert` + audit |
| `/app/api/item/{id}/comment` | POST | collaborator | `backlog_comment` (409 vid konflikt) |
| `/app/api/item/{id}/score` | PATCH | collaborator | `backlog_score` (dito) |
| `/app/api/admin/users|projects|audit|system` | GET | admin | acl + AuditLog.query() |

**Mönster:** `_require_user` → `_acl()` → `enforce()` → anropa **samma tools/*-funktion som MCP-verktyget** → audit-logga muterande. Ingen logikduplicering.

### 7.4 Backend-tillägg

- `acl.py`: `is_admin(user_id)`; admin kortsluter `enforce` (owner överallt)
- `safety/audit.py`: `query(user?, project?, tool?, ok?, since?, limit, offset)`
- `tools/calendar.py`: bryt ut `calendar_setup`/`calendar_status`-kärnan så den kan nås från web-routes
- Per-user-lösenord: acl.yaml-fält + uppdaterad `_verify_password(user, provided)`

### 7.5 Säkerhet
- Alla `/app/api/*` bakom cookie + `enforce` per anrop (aldrig lita på klientens rollflagga)
- Muterande anrop: samma rollkrav som MCP-API.md (facit)
- Destruktiva åtgärder kräver confirm-dialog (SAFETY §8)
- Admin-endpoints returnerar aldrig hemligheter
- Rendering med `textContent`/DOM-bygge — ingen `innerHTML` med användardata
- CSRF: `Content-Type: application/json` + SameSite=lax + origin-check

---

## Nyckelfynd att agera på före bygge

1. **Admin-roll saknas** i `acl.py` — måste specas in i acl.yaml-schemat
2. **Delat lösenord** i `MEMAIX_LOGIN_PASSWORD_HASH` blockerar multi-user-UI
3. **`calendar_setup`-logiken** ligger fast i MCP-dekoratorn i `server.py` — måste brytas ut
4. **`AuditLog`** behöver en `query()`-metod för admin-fliken

Allt annat är tunna lager ovanpå kod som redan finns.
