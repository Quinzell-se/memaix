# Funktion #24 — Webb-UI Utkorg + Admin (Fas C)

SPDX-License-Identifier: AGPL-3.0-or-later

Designdok + byggspec för Memaix webb-UI Fas C: utkorgens godkännandeflöde i
webbläsaren, kortmodal med kommentarer och V/C/R-poängstegare, och admins
läsvyer för användare, projekt, audit-logg och systemhälsa. Fas C bygger på
app-shellet och API-grunden från Fas A+B (MEX-022+023) och integreras med
utkorgslogiken från Funktion #3 (`FEATURE-APPROVAL-OUTBOX.md`).

All utkorgslogik (ActionQueue, Policy, Execute) är definierad i Funktion #3.
Det här dokumentet specificerar enbart webb-UI-lagret — sidor, komponenter,
API-routes och JS — som exponerar den befintliga backend-logiken.

---

## 1. Vad användaren upplever

### 1.1 Utkorgssidan `/app/outbox`

Navigeringsbadgen bredvid "Utkorg" i sidebaren visar antalet väntande ärenden
och uppdateras var 10:e sekund. Badge pausar när tabben är dold (Page Visibility
API). En röd siffra indikerar att åtgärd krävs.

Sidan har två flikar: **Väntande** och **Avgjorda**. Projektfilter-dropdown
ovanför listan (alla projekt användaren kan se). Varje rad i Väntande-listan:

```
⏳  email_send · acme · förfaller om 68 h
    Till: kund@example.com — "Offert v2, 12 rader"
                                        [Förhandsgranska]  [Avvisa]  [Godkänn ✓]
```

Statusfärgkodning: `pending` = gul vänsterkant, `executed` = grön, `rejected` =
grå, `expired` = grå med linje genom, `failed` = röd.

"Godkänn" och "Avvisa"-knappar är dolda för reader (rollen som gatade åtgärden
kräver kontrolleras server-side; client-side döljer knapparna baserat på
`me.role_map[project]`). Reader kan fortfarande se listan och förhandsgranska.

Klick "Godkänn" → optimistisk flytt av raden till Avgjorda + spinner → `POST
/app/api/outbox/{id}/approve` → vid konflikt (`409`): toast "Redan avgjort av
{decided_by}" och raden laddas om med korrekt status.

Klick "Avvisa" → liten inline-form dyker upp under raden: `<textarea
placeholder="Orsak (valfritt)">` + [Bekräfta avvisning] [Avbryt]. Bekräftelse →
`POST /app/api/outbox/{id}/reject {reason}`.

Klick "Förhandsgranska" → öppnar preview-modal med full action-detalj.

### 1.2 Preview-modal

```
┌─ email_send — acme ──────────────────────────────── [✕] ┐
│ Status:    ⏳ Väntande                                    │
│ Initierad: alice · 2026-07-03 14:22 (68 h kvar)          │
│                                                           │
│ Till:      kund@example.com                               │
│ Ämne:      Offert version 2                               │
│                                                           │
│ ─────────────────────────────────────────────────────     │
│ Hej,                                                      │
│ Bifogat finner du vår uppdaterade offert…                 │
│ (trunkerat efter 20 rader — full text i MCP-klienten)     │
│ ─────────────────────────────────────────────────────     │
│                           [Stäng]  [Avvisa]  [Godkänn ✓] │
└───────────────────────────────────────────────────────────┘
```

Full `args_json` visas formaterad per verktygstyp (se §4.2). Inte rå JSON —
strukturerad rendering med etiketter. "Trunkerat"-not om body > 20 rader.

Avgjorda ärenden visar ytterligare fält: Avgjord av / Tidpunkt / Orsak (vid
avvisning) / Resultat (vid utfört eller misslyckat).

### 1.3 Kortmodal med kommentarer och V/C/R

Varje Kanban-kort kan öppnas med ett klick på korttiteln (inte på drag-handtaget).
Deep-link: `?item=BL-123` i URL:en öppnar modalen direkt. URL:en uppdateras
(`history.replaceState`) när modalen öppnas och återställs när den stängs.

```
┌─ BL-42 · Implementera onboarding-intervju ─────── [✕] ┐
│ Status: triaged  Sprint: 2026-Q3  Projekt: acme         │
│ Skapad: 2026-06-15  Uppdaterad: 2026-07-01              │
│                                                         │
│ Beskrivning:                                            │
│ Skapa ett strukturerat intervjuflöde för nya…           │
│                                                         │
│ V/C/R-poäng ──────────────────────────────────────      │
│ Värde (V):    [1][-][+][2][3][4][5]   ← stepper       │
│ Komplexitet:  [1][-][+][2][3][4][5]                     │
│ Risk (R):     [1][-][+][2][3][4][5]                     │
│ (Redigering kräver collaborator-roll)                   │
│                                                         │
│ Kommentarer ──────────────────────────────────────      │
│ alice · 2026-07-01 · "Diskuterat med Bob, prioritera"   │
│ bob   · 2026-07-02 · "Klart för sprint-planering"       │
│                                                         │
│ [Ny kommentar…                            ] [Skicka]    │
│ (Kommentering kräver collaborator-roll)                 │
└─────────────────────────────────────────────────────────┘
```

V/C/R-steppers är `<button>` med `-`/`+` och en siffra i mitten (1–5). Disabled
och förklarande text "Kräver collaborator-roll" för reader. Varje stepper-ändring
triggar `PATCH /app/api/board/card/{id}/score {v, c, r}` (debounce 800ms — inte
varje knapptryck).

Kommentarer hämtas från `GET /app/api/board/card/{id}/comments`. Ny kommentar →
`POST /app/api/board/card/{id}/comments {text}` → optimistisk infogning i listan.

### 1.4 Admin-sektionen `/app/admin`

Länken i sidebaren är dold för alla utom `is_admin = true`. Sidan har fyra flikar:
Användare, Projekt, Audit och System. Alla vyer är **skrivskyddade** i Fas C —
skrivoperationer (kill-switch, grants-ändring, MFA-hantering) hör till Fas D.

**Flik Användare:**

En tabell med användare som rader och projekt som kolumner. Cellen visar en
roll-chip (`owner`/`collaborator`/`reader`) eller em-dash om användaren saknar
grant för det projektet. MFA-status visas som `🔐` (aktiv) eller `⚠️ MFA saknas`
per rad. (MFA byggs i Fas D — kolumnen visar alltid "⚠️ MFA saknas" i MVP med
en note "MFA implementeras i Fas D".)

Klick på en cell visar en tooltip med grant-detaljer. Ingen redigering i Fas C.

**Flik Projekt:**

En lista med alla projekt. Per rad:
- Projektnamn
- `allow_send`: `✓` (grön) eller `✗` (grå)
- `outbox`-läge: `auto` (grå chip) eller `review` (gul chip)
- Antal användare med grant
- Vault-katalog (trunkerad)

Klick på en rad expanderar en detalj-rad med projektets fulla konfiguration från
`acl.yaml` (formaterad, inte rå YAML). Inga redigeringsfält.

**Flik Audit:**

Filtrerbar tabell som anropar `AuditLog.query()`. Filter-kontroller:

```
[Användare ▾]  [Projekt ▾]  [Verktyg ▾]  [✓ OK  ✗ Fel  Båda]  [Sedan: datum]
                                                    [Filtrera]
```

Tabellkolumner: Tidpunkt (relativ) · Användare · Projekt · Verktyg · OK · Detalj.

Felade rader (`ok = False`) är expanderbara: klick på raden visar `detail`-fältet
(felinformation) i en indragen sub-rad med `.mono`-typsnitt.

Paginering: 50 rader per sida, "Visa fler"-knapp (append, inte byte av sida).
Ingen automatisk refresh — "Uppdatera"-knapp laddar om senaste filter.

**Flik System:**

Tre sektioner: Hälsa, Version och OAuth-leverantörer.

```
┌ Hälsa ────────────────────────────────────────────────────┐
│ vault_writable     ✓ ok                                   │
│ outbox_db          ✓ ok                                   │
│ token_db           ✓ ok     (om konfigurerat)             │
│ calendar_api       ⚠ degraded  "token expires in 2h"      │
└───────────────────────────────────────────────────────────┘

┌ Version ──────────────────────────────────────────────────┐
│ memaix-gateway   0.9.3                                    │
│ python           3.12.4                                   │
│ git-sha          a1b2c3d (2026-07-01)                     │
└───────────────────────────────────────────────────────────┘

┌ OAuth-leverantörer ───────────────────────────────────────┐
│ google       konfigurerad  (client_id: …345f)             │
│ microsoft    ej konfigurerad                              │
└───────────────────────────────────────────────────────────┘
```

**Viktigt:** OAuth-leverantör-sektionen visar aldrig secrets — enbart om
`client_id` finns (trunkerat) och om leverantören är konfigurerad. Endpoint
`GET /app/api/admin/system` hämtar data från `doctor.py`-funktionerna +
`config.py`. Aldrig `client_secret`, aldrig fullständiga API-nycklar.

---

## 2. Nyckelbeslut

1. **Utkorg-poll pausar vid dold tab.** `pollBadge()` (definierad i `app.js`, Fas A)
   kontrollerar `document.visibilityState` varje tick. Utkorgssidan startar
   dessutom en separat lokal poll för listvyn (var 10 s) som också pausar.

2. **Optimistisk UI för godkänn/avvisa, konflikthantering via 409.** Raden flyttas
   omedelbart i klientens DOM. Vid `409` från servern: toast + återhämta rad från
   `GET /app/api/outbox/{id}` och rendera med rätt status och `decided_by`.

3. **Deep-link via `?item=BL-123` utan SPA.** Sidan laddas normalt; `board.js`
   läser `URLSearchParams` vid `DOMContentLoaded` och öppnar kortmodalen om
   `item`-param finns. Stängning av modalen → `history.replaceState` tar bort
   param utan sidladdning.

4. **V/C/R-stepper är debounce-drivna PATCH-anrop.** Inte ett formulär med
   submit. Varje stepper-ändring arm:ar en 800ms debounce-timer; om ytterligare
   ändring sker inom 800ms återstartas timern. Det skickar ett enda PATCH oavsett
   hur snabbt användaren klickar.

5. **Admin-vyer är strikt läsvyer i Fas C.** Inga formulärfält som modifierar
   data (utom "Filtrera" och "Visa fler"). Begränsningar finns både i HTML
   (inga edit-kontroller) och server-side (alla admin write-routes saknas tills
   Fas D). Detta begränsar angrepp på admin-sektionen.

6. **`AuditLog.query()` anropas direkt.** `GET /app/api/admin/audit` är ett
   tunt lager som läser filter-params och delegerar till `safety/audit.py`.
   Inga parallella implementationer.

7. **System-endpoint exponerar aldrig secrets.** `GET /app/api/admin/system`
   hämtar hälsodata från `doctor.py` och returnerar en rensad `oauth_providers`-lista:
   `[{"provider": "google", "configured": True, "client_id_suffix": "…345f"}]`.
   `client_secret` och `refresh_token` ingår aldrig.

8. **Kortmodal-kommentarer lagras i board-backend.** `backlog_comment()` i
   `tools/backlog.py` är det befintliga MCP-verktyget; `/app/api/board/card/{id}/comments`
   är det tunna webb-lagret. Samma datakälla, inget duplicerat.

---

## 3. Översikt

```
Browser                          Gateway (Starlette)
───────                          ───────────────────

── Utkorg ──────────────────────────────────────────────────

GET /app/outbox  ─────────────► _html_with_locale("outbox")
  JS poll (10s): /app/api/outbox (pausa vid hidden-tab)
     ───────────────────────────► GET /app/api/outbox?project=&status=pending
                  ◄──────────────  ActionQueue.list() → [{id, tool, project, preview, …}]
  "Godkänn":
     ───────────────────────────► POST /app/api/outbox/{id}/approve
                                  outbox_approve(acl, user, id)
                  ◄──────────────  200 {ok, result} | 409 {conflict, decided_by}
  "Avvisa":
     ───────────────────────────► POST /app/api/outbox/{id}/reject {reason}
                                  outbox_reject(acl, user, id, reason)
                  ◄──────────────  200 {ok} | 409 {conflict}

── Kortmodal ───────────────────────────────────────────────

GET /app/board?item=BL-42 ────► _html_with_locale("board") + modal auto-open
  ───────────────────────────►  GET /app/api/board/card/BL-42
                  ◄─────────────  backlog_get(acl, user, project, "BL-42")
  ───────────────────────────►  GET /app/api/board/card/BL-42/comments
                  ◄─────────────  backlog_comments(acl, user, project, "BL-42")
  Stepper (debounce 800ms):
     ─────────────────────────►  PATCH /app/api/board/card/BL-42/score {v,c,r}
                                  backlog_score(acl, user, project, "BL-42", v,c,r)
  Ny kommentar:
     ─────────────────────────►  POST /app/api/board/card/BL-42/comments {text}
                                  backlog_comment(acl, user, project, "BL-42", text)

── Admin ───────────────────────────────────────────────────

GET /app/admin   ─────────────► _html_with_locale("admin")  (is_admin: true)
  ─────────────────────────────►  GET /app/api/admin/users
                  ◄──────────────  Acl.from_config() → grants-matris
  ─────────────────────────────►  GET /app/api/admin/projects
                  ◄──────────────  Acl.from_config() → projekt-lista
  ─────────────────────────────►  GET /app/api/admin/audit?user=&project=&tool=&ok=&since=
                                  AuditLog.query(filters)
  ─────────────────────────────►  GET /app/api/admin/system
                                  doctor.run_checks() + config.version_info()
```

---

## 4. Komponenter

### 4.1 `web/pages/outbox.html` + `web/static/outbox.js`

**HTML-struktur:**

```html
<div class="page-header">
  <h1>Utkorg</h1>
  <select id="outbox-project-filter">
    <option value="">Alla projekt</option>
  </select>
</div>
<div class="tabs" role="tablist">
  <button class="tab-active" data-tab="pending">
    Väntande <span id="pending-count" class="badge badge-warning"></span>
  </button>
  <button data-tab="decided">Avgjorda</button>
</div>
<div id="tab-pending"  class="tab-panel">
  <ul id="outbox-list" class="outbox-list"></ul>
  <p id="outbox-empty" class="empty-state" hidden>Inga väntande ärenden.</p>
</div>
<div id="tab-decided"  class="tab-panel" hidden>
  <ul id="decided-list" class="outbox-list"></ul>
</div>
```

**Rad-rendering i `outbox.js`:**

Alla fält byggs via `createElement + textContent` — aldrig via stränginterpolation
i DOM. Datum-/tidsfält via `<time>`, statusfärgkodning via `dataset.status`.

```js
function renderOutboxRow(item, canDecide) {
  const li = document.createElement('li');
  li.className = 'outbox-row';
  li.dataset.status = item.status;
  li.dataset.id = item.id;

  const meta = document.createElement('div');
  meta.className = 'outbox-meta';

  const tool = document.createElement('span');
  tool.className = 'mono';
  tool.textContent = item.tool;         // textContent — aldrig stränginterpolation

  const proj = document.createElement('span');
  proj.className = 'muted';
  proj.textContent = item.project;

  const ttl = document.createElement('time');
  ttl.textContent = formatTTL(item.expires_at);
  meta.append(tool, ' · ', proj, ' · ', ttl);

  const preview = document.createElement('div');
  preview.className = 'outbox-preview muted';
  preview.textContent = item.preview;   // preview är plain text från outbox/preview.py

  const actions = document.createElement('div');
  actions.className = 'outbox-actions';

  const previewBtn = document.createElement('button');
  previewBtn.className = 'btn';
  previewBtn.textContent = t('outbox_preview');
  previewBtn.addEventListener('click', () => openPreviewModal(item));
  actions.append(previewBtn);

  if (canDecide && item.status === 'pending') {
    const rejectBtn = document.createElement('button');
    rejectBtn.className = 'btn btn-danger';
    rejectBtn.textContent = t('outbox_reject');
    rejectBtn.addEventListener('click', () => openRejectForm(li, item.id));

    const approveBtn = document.createElement('button');
    approveBtn.className = 'btn btn-primary';
    approveBtn.textContent = t('outbox_approve');
    approveBtn.addEventListener('click', () => approveItem(item.id, li));
    actions.append(rejectBtn, approveBtn);
  }

  li.append(meta, preview, actions);
  return li;
}
```

**Godkänn-flöde:**

```js
async function approveItem(id, rowEl) {
  rowEl.classList.add('deciding');
  rowEl.querySelector('.btn-primary').disabled = true;
  try {
    await api('POST', `/app/api/outbox/${id}/approve`);
    rowEl.classList.remove('deciding');
    rowEl.dataset.status = 'executed';
    toast(t('outbox_approved_ok'), 'success');
  } catch (err) {
    if (err.httpStatus === 409) {
      const body = await err.json?.() ?? {};
      const decidedBy = body.decided_by ?? '';
      const msg = document.createElement('span');
      msg.textContent = t('outbox_conflict') + ' ' + decidedBy;  // textContent
      toast(msg.textContent, 'warning');
      const fresh = await api('GET', `/app/api/outbox/${id}`);
      rowEl.replaceWith(renderOutboxRow(fresh, false));
    } else {
      toast(err.message, 'error');
      rowEl.classList.remove('deciding');
      rowEl.querySelector('.btn-primary').disabled = false;
    }
  }
}
```

**Avvisa-form (inline):**

```js
function openRejectForm(rowEl, id) {
  const existing = rowEl.querySelector('.reject-form');
  if (existing) { existing.remove(); return; }   // toggle

  const form = document.createElement('div');
  form.className = 'reject-form surface';

  const textarea = document.createElement('textarea');
  textarea.placeholder = t('outbox_reject_reason_placeholder');
  textarea.rows = 2;

  const confirmBtn = document.createElement('button');
  confirmBtn.className = 'btn btn-danger';
  confirmBtn.textContent = t('outbox_reject_confirm');

  const cancelBtn = document.createElement('button');
  cancelBtn.className = 'btn';
  cancelBtn.textContent = t('cancel');
  cancelBtn.addEventListener('click', () => form.remove());

  confirmBtn.addEventListener('click', async () => {
    await api('POST', `/app/api/outbox/${id}/reject`,
              { reason: textarea.value });
    rowEl.closest('li').dataset.status = 'rejected';
    form.remove();
    toast(t('outbox_rejected_ok'), 'info');
  });

  form.append(textarea, confirmBtn, cancelBtn);
  rowEl.append(form);
}
```

**Poll i utkorgen (lokal, utöver badge):**

```js
let outboxPoll = null;

function startOutboxPoll() {
  outboxPoll = setInterval(async () => {
    if (document.visibilityState === 'hidden') return;
    const project = document.querySelector('#outbox-project-filter').value;
    const items = await api('GET',
      `/app/api/outbox?status=pending&project=${encodeURIComponent(project)}`);
    reconcileOutboxList(items);
  }, 10_000);
}
document.addEventListener('DOMContentLoaded', startOutboxPoll);
```

`reconcileOutboxList` jämför `item.id`-uppsättningen mot befintliga rader:
lägg till nya, ta bort försvunna (avgjorda av annan). Rader med klassen
`deciding` (optimistisk övergång pågår) skyddas från extern override.

### 4.2 Preview-modal — strukturerad rendering per verktygstyp

`openPreviewModal(item)` anropar `modal(buildPreviewEl(item))`.
`buildPreviewEl` är en `switch (item.tool)` som returnerar ett DOM-element.
All data sätts via `textContent`. Det enda undantaget är `<pre>` med
`JSON.stringify` för okänd verktygstyp — `JSON.stringify` producerar alltid
ren text utan HTML-tolkning.

```js
function buildPreviewEl(item) {
  const wrap = document.createElement('div');
  wrap.className = 'preview-modal-content';

  const header = document.createElement('div');
  header.className = 'preview-header surface';
  appendLabelValue(header, t('preview_tool'),    item.tool);
  appendLabelValue(header, t('preview_project'), item.project);
  appendLabelValue(header, t('preview_status'),  t('status_' + item.status));
  appendLabelValue(header, t('preview_created'), formatRelative(item.created_at));
  appendLabelValue(header, t('preview_expires'), formatTTL(item.expires_at));
  wrap.append(header);

  const body = document.createElement('div');
  body.className = 'preview-body';

  switch (item.tool) {
    case 'email_send':
      appendLabelValue(body, t('email_to'),      item.args.to);
      if (item.args.cc) appendLabelValue(body, t('email_cc'), item.args.cc);
      appendLabelValue(body, t('email_subject'), item.args.subject);
      appendBodyPreview(body, item.args.body);
      break;
    case 'calendar_create':
    case 'calendar_update':
      appendLabelValue(body, t('cal_title'),  item.args.title);
      appendLabelValue(body, t('cal_start'),  item.args.start);
      appendLabelValue(body, t('cal_end'),    item.args.end);
      if (item.args.location)
        appendLabelValue(body, t('cal_location'), item.args.location);
      if (item.args.attendees?.length)
        appendLabelValue(body, t('cal_attendees'),
                         item.args.attendees.join(', '));
      break;
    default: {
      const pre = document.createElement('pre');
      pre.className = 'mono surface';
      pre.textContent = JSON.stringify(item.args, null, 2);
      body.append(pre);
    }
  }

  wrap.append(body);

  if (item.status !== 'pending') {
    const decided = document.createElement('div');
    decided.className = 'decided-section surface';
    appendLabelValue(decided, t('decided_by'),  item.decided_by ?? '—');
    appendLabelValue(decided, t('decided_at'),  formatRelative(item.decided_at));
    if (item.reason)
      appendLabelValue(decided, t('reject_reason'), item.reason);
    wrap.append(decided);
  }

  return wrap;
}

function appendLabelValue(parent, label, value) {
  const row = document.createElement('div');
  row.className = 'label-value-row';
  const lbl = document.createElement('span');
  lbl.className = 'muted';
  lbl.textContent = label + ':';
  const val = document.createElement('span');
  val.textContent = value ?? '—';
  row.append(lbl, val);
  parent.append(row);
}
```

### 4.3 Kortmodal i board

`board.js` utökas med kortmodal-stöd. Befintlig `board.html` renderar kort som
`<div class="card" data-id="BL-42">`. Klick på `.card-title` öppnar modal;
klick på `.drag-handle` startar drag som vanligt.

```js
document.addEventListener('click', e => {
  const title = e.target.closest('.card-title');
  if (title) {
    const id = title.closest('[data-id]').dataset.id;
    openCardModal(id);
  }
});

async function openCardModal(id) {
  const project = new URLSearchParams(location.search).get('project')
               ?? localStorage.getItem('memaix_project');
  history.replaceState(null, '', `?project=${project}&item=${id}`);

  const [card, comments, me] = await Promise.all([
    api('GET', `/app/api/board/card/${id}?project=${project}`),
    api('GET', `/app/api/board/card/${id}/comments?project=${project}`),
    api('GET', '/app/api/me')
  ]);

  const role = me.role_map[project] ?? 'reader';
  const canEdit = role === 'collaborator' || role === 'owner' || me.is_admin;

  const handle = modal(buildCardModalEl(card, comments, canEdit, project));
  handle.onClose = () => {
    history.replaceState(null, '', `?project=${project}`);
  };
}
```

**Deep-link vid sidladdning:**

```js
document.addEventListener('DOMContentLoaded', () => {
  const params = new URLSearchParams(location.search);
  const itemId = params.get('item');
  if (itemId) openCardModal(itemId);
});
```

**V/C/R-stepper-komponent:**

```js
function buildStepper(label, field, value, canEdit) {
  const wrap = document.createElement('div');
  wrap.className = 'vcr-stepper';

  const lbl = document.createElement('span');
  lbl.textContent = label + ':';

  const num = document.createElement('span');
  num.className = 'stepper-value';
  num.textContent = value ?? '—';

  let current = value ?? 3;
  let debounceTimer = null;

  const minus = document.createElement('button');
  minus.textContent = '−';
  minus.disabled = !canEdit || current <= 1;

  const plus = document.createElement('button');
  plus.textContent = '+';
  plus.disabled = !canEdit || current >= 5;

  function onChange(delta) {
    current = Math.min(5, Math.max(1, current + delta));
    num.textContent = current;
    minus.disabled = current <= 1;
    plus.disabled  = current >= 5;
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      wrap.dispatchEvent(new CustomEvent('vcr-change', {
        bubbles: true, detail: { field, value: current }
      }));
    }, 800);
  }

  minus.addEventListener('click', () => onChange(-1));
  plus.addEventListener('click',  () => onChange(+1));

  if (!canEdit) {
    const note = document.createElement('span');
    note.className = 'muted';
    note.textContent = t('requires_collaborator');
    wrap.append(lbl, minus, num, plus, note);
  } else {
    wrap.append(lbl, minus, num, plus);
  }

  return wrap;
}
```

Yttre kodlager lyssnar på `vcr-change` från modalens container och samlar alla
tre fält; PATCH-anropet skickar `{v, c, r}` samlat.

**Kommentarformulär:**

```js
function buildCommentForm(cardId, project, listEl, canEdit) {
  const form = document.createElement('div');
  form.className = 'comment-form';

  const textarea = document.createElement('textarea');
  textarea.placeholder = canEdit ? t('add_comment_placeholder')
                                 : t('requires_collaborator');
  textarea.rows = 3;
  textarea.disabled = !canEdit;

  const submit = document.createElement('button');
  submit.className = 'btn btn-primary';
  submit.textContent = t('comment_submit');
  submit.disabled = !canEdit;

  submit.addEventListener('click', async () => {
    const text = textarea.value.trim();
    if (!text) return;
    submit.disabled = true;
    const saved = textarea.value;
    textarea.value = '';
    try {
      const comment = await api('POST',
        `/app/api/board/card/${cardId}/comments`,
        { project, text });
      appendCommentEl(listEl, comment);
    } catch (err) {
      textarea.value = saved;
      toast(err.message, 'error');
    } finally {
      submit.disabled = false;
    }
  });

  form.append(textarea, submit);
  return form;
}
```

### 4.4 `web/pages/admin.html` + `web/static/admin.js`

**Sidskydd i route-handler:**

```python
async def app_admin(request: Request) -> HTMLResponse:
    acl = Acl.from_config()
    user = _require_user(request)
    if not acl.is_admin(user):
        return Response(status_code=403, content="Åtkomst nekad.")
    locale = _get_locale(request)
    return HTMLResponse(_html_with_locale("admin", locale))
```

**Flik Användare — matris-rendering:**

`GET /app/api/admin/users` returnerar:

```json
{
  "users": ["alice", "bob", "carol"],
  "projects": ["acme", "project-a"],
  "grants": {
    "alice": {"acme": "owner", "project-a": "collaborator"},
    "bob":   {"acme": "collaborator"},
    "carol": {}
  },
  "mfa": {"alice": false, "bob": false, "carol": false}
}
```

`admin.js` bygger `<table>` med `<thead>` (projekt-kolumner) och `<tbody>`
(användar-rader). Allt via `createElement + textContent`.

```js
function buildUsersTable(data) {
  const table = document.createElement('table');
  table.className = 'admin-table';

  const thead = document.createElement('thead');
  const headerRow = document.createElement('tr');
  ['Användare', ...data.projects, 'MFA'].forEach(col => {
    const th = document.createElement('th');
    th.textContent = col;
    headerRow.append(th);
  });
  thead.append(headerRow);
  table.append(thead);

  const tbody = document.createElement('tbody');
  data.users.forEach(user => {
    const tr = document.createElement('tr');
    const nameTd = document.createElement('td');
    nameTd.textContent = user;
    tr.append(nameTd);

    data.projects.forEach(proj => {
      const td = document.createElement('td');
      const role = data.grants[user]?.[proj];
      if (role) {
        const chip = document.createElement('span');
        chip.className = `role-chip role-${role}`;
        chip.textContent = role;
        td.append(chip);
      } else {
        const dash = document.createElement('span');
        dash.className = 'muted';
        dash.textContent = '—';
        td.append(dash);
      }
      tr.append(td);
    });

    const mfaTd = document.createElement('td');
    mfaTd.textContent = data.mfa[user] ? '🔐' : '⚠️ MFA saknas';
    tr.append(mfaTd);
    tbody.append(tr);
  });
  table.append(tbody);
  return table;
}
```

`.role-chip.role-owner { background:var(--primary-light); color:var(--primary); }`
`.role-chip.role-collaborator { background:rgba(148,163,184,.15); color:var(--muted); }`
`.role-chip.role-reader { background:rgba(148,163,184,.1); color:var(--muted); }`

En diskret note under tabellen: *"MFA-hantering implementeras i Fas D."*

**Flik Projekt — expand-rad:**

```js
function buildDetailEl(proj) {
  const wrap = document.createElement('div');
  wrap.className = 'surface mono project-detail';
  const items = [
    ['vault_path',  proj.vault_path],
    ['outbox_mode', proj.outbox_mode ?? 'auto'],
    ['allow_send',  proj.allow_send ? 'true' : 'false'],
    ['allowlist',   (proj.allowlist ?? []).join(', ') || '(tom)'],
  ];
  items.forEach(([k, v]) => {
    const row = document.createElement('div');
    const key = document.createElement('span');
    key.className = 'muted';
    key.textContent = k + ': ';
    const val = document.createElement('span');
    val.textContent = v;
    row.append(key, val);
    wrap.append(row);
  });
  return wrap;
}
```

**Flik Audit:**

```js
let currentOffset = 0;

async function loadAudit(append = false) {
  const params = new URLSearchParams({
    user:    userFilter.value,
    project: projectFilter.value,
    tool:    toolFilter.value,
    ok:      okFilter.value,
    since:   sinceFilter.value,
    offset:  append ? currentOffset : 0,
    limit:   50,
  });
  const { entries, total } = await api('GET',
    `/app/api/admin/audit?${params}`);

  if (!append) {
    while (auditTbody.firstChild) auditTbody.firstChild.remove();
  }
  entries.forEach(e => auditTbody.append(renderAuditRow(e)));
  currentOffset = (append ? currentOffset : 0) + entries.length;
  showMoreBtn.hidden = currentOffset >= total;
}

function renderAuditRow(entry) {
  const tr = document.createElement('tr');
  tr.className = entry.ok ? '' : 'audit-row-error';

  [
    formatRelative(entry.ts),
    entry.user,
    entry.project ?? '—',
    entry.tool,
  ].forEach(text => {
    const td = document.createElement('td');
    td.textContent = text;
    tr.append(td);
  });

  const okTd = document.createElement('td');
  okTd.textContent = entry.ok ? '✓' : '✗';
  okTd.className = entry.ok ? 'text-success' : 'text-danger';
  tr.append(okTd);

  if (!entry.ok && entry.detail) {
    tr.style.cursor = 'pointer';
    tr.addEventListener('click', () => toggleAuditDetail(tr, entry.detail));
  }

  return tr;
}

function toggleAuditDetail(tr, detail) {
  const next = tr.nextElementSibling;
  if (next?.classList.contains('audit-detail-row')) {
    next.remove();
    return;
  }
  const detailTr = document.createElement('tr');
  detailTr.className = 'audit-detail-row';
  const td = document.createElement('td');
  td.colSpan = 6;
  td.className = 'mono surface';
  td.style.padding = '8px 16px';
  td.textContent = detail;   // aldrig tolkas som HTML
  detailTr.append(td);
  tr.after(detailTr);
}
```

**Flik System:**

```js
async function loadSystem() {
  const data = await api('GET', '/app/api/admin/system');
  renderHealth(data.health);
  renderVersion(data.version);
  renderOAuthProviders(data.oauth_providers);
}

function renderHealth(checks) {
  const section = document.querySelector('#health-section');
  while (section.firstChild) section.firstChild.remove();

  checks.forEach(({ check, status, detail }) => {
    const row = document.createElement('div');
    row.className = 'health-row';

    const icon = document.createElement('span');
    icon.textContent = status === 'ok' ? '✓'
                    : status === 'degraded' ? '⚠' : '✗';
    icon.className   = status === 'ok' ? 'text-success'
                    : status === 'degraded' ? 'text-warning' : 'text-danger';

    const name = document.createElement('span');
    name.className = 'mono';
    name.textContent = check;

    const det = document.createElement('span');
    det.className = 'muted';
    det.textContent = detail ?? '';

    row.append(icon, name, det);
    section.append(row);
  });
}
```

`.text-success { color:var(--success); }` `.text-warning { color:var(--warning); }`
`.text-danger { color:var(--danger); }`

### 4.5 `web/api/outbox.py` — Backend för utkorgssidan

```python
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Webb-API för utkorgen — tunnt lager ovanpå outbox/queue.py + outbox/execute.py."""
from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse

from ..acl import Acl
from ..outbox.queue import ActionQueue
from ..outbox.execute import execute_pending


async def api_outbox_list(request: Request) -> JSONResponse:
    """GET /app/api/outbox?project=&status=pending"""
    acl   = Acl.from_config()
    user  = _require_user(request)
    proj  = request.query_params.get("project") or None
    status = request.query_params.get("status") or "pending"
    q     = ActionQueue()
    projects = [proj] if proj else acl.visible_projects(user)
    items = q.list(projects=projects, status=status)
    return JSONResponse(items)


async def api_outbox_get(request: Request) -> JSONResponse:
    """GET /app/api/outbox/{id}"""
    acl  = Acl.from_config()
    user = _require_user(request)
    q    = ActionQueue()
    item = q.get(request.path_params["id"])
    if not item:
        return JSONResponse({"error": "not_found"}, status_code=404)
    acl.enforce(user, item["project"], "reader")
    return JSONResponse(item)


async def api_outbox_approve(request: Request) -> JSONResponse:
    """POST /app/api/outbox/{id}/approve"""
    acl  = Acl.from_config()
    user = _require_user(request)
    q    = ActionQueue()
    item = q.get(request.path_params["id"])
    if not item:
        return JSONResponse({"error": "not_found"}, status_code=404)
    required_role = _tool_required_role(item["tool"])
    acl.enforce(user, item["project"], required_role)
    claimed = q.claim_for_decision(item["id"], "approved", user)
    if claimed is None:
        decided = q.get(item["id"])
        return JSONResponse(
            {"conflict": True, "decided_by": decided.get("decided_by")},
            status_code=409
        )
    result = execute_pending(acl, claimed)
    return JSONResponse({"ok": True, "result": result})


async def api_outbox_reject(request: Request) -> JSONResponse:
    """POST /app/api/outbox/{id}/reject {reason}"""
    acl  = Acl.from_config()
    user = _require_user(request)
    body = await request.json()
    q    = ActionQueue()
    item = q.get(request.path_params["id"])
    if not item:
        return JSONResponse({"error": "not_found"}, status_code=404)
    required_role = _tool_required_role(item["tool"])
    acl.enforce(user, item["project"], required_role)
    claimed = q.claim_for_decision(item["id"], "rejected", user)
    if claimed is None:
        decided = q.get(item["id"])
        return JSONResponse(
            {"conflict": True, "decided_by": decided.get("decided_by")},
            status_code=409
        )
    q.record_result(item["id"], "rejected", {"reason": body.get("reason", "")})
    return JSONResponse({"ok": True})


_TOOL_ROLE: dict[str, str] = {
    "email_send":      "owner",
    "calendar_create": "owner",
    "calendar_update": "owner",
}

def _tool_required_role(tool: str) -> str:
    return _TOOL_ROLE.get(tool, "owner")  # konservativt default: owner
```

### 4.6 `web/api/admin.py` — Backend för admin-vyer

```python
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Webb-API för admin-läsvyer — tunnt lager ovanpå Acl, AuditLog, doctor."""
from __future__ import annotations

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse

from ..acl import Acl
from ..safety.audit import AuditLog
from .. import doctor as doc
from .. import config as cfg


def _require_admin(request: Request, acl: Acl) -> str:
    """Hämta autentiserad admin-användare; kastar 403 om inte admin."""
    user = _require_user(request)
    if not acl.is_admin(user):
        raise HTTPException(status_code=403, detail="admin_required")
    return user


async def api_admin_users(request: Request) -> JSONResponse:
    """GET /app/api/admin/users → grants-matris"""
    acl  = Acl.from_config()
    _require_admin(request, acl)
    users    = acl.all_users()
    projects = acl.all_projects()
    grants   = {u: acl.grants(u) for u in users}
    return JSONResponse({
        "users":    users,
        "projects": projects,
        "grants":   grants,
        "mfa":      {u: False for u in users},  # MFA byggs i Fas D
    })


async def api_admin_projects(request: Request) -> JSONResponse:
    """GET /app/api/admin/projects"""
    acl = Acl.from_config()
    _require_admin(request, acl)
    projects = acl.all_projects()
    result = []
    for proj in projects:
        pcfg = acl.project_config(proj)
        result.append({
            "name":       proj,
            "vault_path": str(pcfg.get("vault_path", "")),
            "outbox_mode": pcfg.get("outbox", "auto"),
            "allow_send": pcfg.get("allow_send", False),
            "allowlist":  pcfg.get("allowlist", []),
            "user_count": len([
                u for u in acl.all_users()
                if proj in acl.grants(u)
            ]),
        })
    return JSONResponse(result)


async def api_admin_audit(request: Request) -> JSONResponse:
    """GET /app/api/admin/audit?user=&project=&tool=&ok=&since=&offset=&limit="""
    acl = Acl.from_config()
    _require_admin(request, acl)
    p = request.query_params
    ok_filter: bool | None = None
    if p.get("ok") == "true":   ok_filter = True
    elif p.get("ok") == "false": ok_filter = False
    log = AuditLog()
    entries, total = log.query(
        user=p.get("user") or None,
        project=p.get("project") or None,
        tool=p.get("tool") or None,
        ok=ok_filter,
        since=p.get("since") or None,
        offset=int(p.get("offset", 0)),
        limit=int(p.get("limit", 50)),
    )
    return JSONResponse({"entries": entries, "total": total})


async def api_admin_system(request: Request) -> JSONResponse:
    """GET /app/api/admin/system — hälsa, version, OAuth-leverantörer (aldrig secrets)"""
    acl = Acl.from_config()
    _require_admin(request, acl)
    health  = doc.run_checks()          # [{check, status, detail}]
    version = cfg.version_info()        # {version, python, git_sha, git_date}
    raw     = cfg.oauth_providers()     # {google: {client_id, client_secret, …}}
    # Rensa secrets — exponera aldrig client_secret, refresh_token, api_key, etc.
    providers = [
        {
            "provider":         name,
            "configured":       bool(pcfg.get("client_id")),
            "client_id_suffix": pcfg["client_id"][-6:] if pcfg.get("client_id") else None,
        }
        for name, pcfg in raw.items()
    ]
    return JSONResponse({
        "health":          health,
        "version":         version,
        "oauth_providers": providers,
    })
```

---

## 5. Backend-routes — komplett tabell (Fas C)

| Metod | Sökväg | Roll | Implementation |
|-------|--------|------|---------------|
| GET | `/app/outbox` | autentiserad (HTML) | `_html_with_locale("outbox")` |
| GET | `/app/api/outbox` | reader | `api_outbox_list()` → `ActionQueue.list()` |
| GET | `/app/api/outbox/{id}` | reader | `api_outbox_get()` → `ActionQueue.get()` |
| POST | `/app/api/outbox/{id}/approve` | owner (per tool) | `api_outbox_approve()` → `execute_pending()` |
| POST | `/app/api/outbox/{id}/reject` | owner (per tool) | `api_outbox_reject()` → `queue.record_result()` |
| GET | `/app/api/board/card/{id}` | reader | `backlog_get()` |
| GET | `/app/api/board/card/{id}/comments` | reader | `backlog_comments()` |
| POST | `/app/api/board/card/{id}/comments` | collaborator | `backlog_comment()` |
| PATCH | `/app/api/board/card/{id}/score` | collaborator | `backlog_score()` |
| GET | `/app/admin` | admin (HTML) | `app_admin()` |
| GET | `/app/api/admin/users` | admin | `api_admin_users()` → `Acl` |
| GET | `/app/api/admin/projects` | admin | `api_admin_projects()` → `Acl` |
| GET | `/app/api/admin/audit` | admin | `api_admin_audit()` → `AuditLog.query()` |
| GET | `/app/api/admin/system` | admin | `api_admin_system()` → `doctor + config` |

---

## 6. Byggordning

Bygg och verifiera i denna ordning. Fas A+B (MEX-022+023) ska vara kompletta och
CI-gröna innan Fas C påbörjas.

1. **`web/api/outbox.py`** — `api_outbox_list/get/approve/reject`. Enhetstester
   med mockad `ActionQueue` och `execute_pending`. Testa konfliktfall (409),
   rollkontroll (reader kan lista men inte godkänna), not_found (404).

2. **`web/pages/outbox.html` + `web/static/outbox.js`** — rad-rendering, godkänn-
   och avvisa-flöde, optimistisk DOM-uppdatering, konflikt-toast. Manuellt test:
   kö ett ärende via `email_send` i review-läge → godkänn i UI → verifiera att
   `_smtp` anropades (testmiljö).

3. **Poll-badge för utkorgen i shell** — `pollBadge('/app/api/me', badgeEl)` +
   Page Visibility API. Manuellt: öppna DevTools Network, bekräfta att poll
   pausar när tabben minimeras.

4. **Preview-modal** — strukturerad rendering per verktygstyp. Enhetstester för
   `buildPreviewEl` med `email_send`- och `calendar_create`-fixtures. Verifiera
   att all data sätts via `textContent`, aldrig tolkas som markup.

5. **Kortmodal — grundvy** — `openCardModal`, hämta `backlog_get` + `backlog_comments`.
   `pytest tests/test_card_modal_routes.py`. Manuellt: klick på korttitel öppnar
   modal med korrekt innehåll; URL uppdateras med `?item=BL-X`.

6. **Deep-link** — `?item=BL-42` vid sidladdning öppnar modalen. Testa via
   direkt URL i nytt fönster.

7. **V/C/R-steppers** — debounce + PATCH-anrop. `pytest tests/test_board_score_route.py`.
   Manuellt: klicka snabbt på `+` fem gånger, bekräfta ett enda PATCH-anrop i
   DevTools Network.

8. **Kommentarformulär** — `backlog_comment` API-route + optimistisk infogning.
   Testa: reader ser formuläret som disabled; collaborator kan skicka; kommentaren
   dyker upp direkt utan reload.

9. **`web/api/admin.py`** — alla fyra admin-endpoints. `pytest tests/test_admin_routes.py`.
   Testa: icke-admin får 403; admin får korrekt JSON; `oauth_providers` innehåller
   aldrig `client_secret` (verifierat av `test_no_secret_leak.py`).

10. **`web/pages/admin.html` + `web/static/admin.js`** — fyra flikar, matris,
    projekt-lista, audit-filter + "Visa fler", system-hälsa. Manuellt: filtrera
    audit på `ok=false`, expandera en feladudit-rad, se detail i mono-typsnitt.

11. **Säkerhetskontroll** — genomgång av alla admin- och utkorgssvar: inga
    `client_secret`, inga lösenordshashes, inga refresh-tokens. Bekräfta med
    `pytest tests/test_no_secret_leak.py`.

12. **CI grön** — `python -m pytest -q` från `gateway/` + `python3 scripts/check-docs-index.py`.

---

## 7. Utvecklingsinstruktioner / Kodkontrakt

### Konventioner

Identiska med Fas A+B (se `FEATURE-WEB-UI-MVP.md` §7). Tilläggskonventioner:

- **All användardata via `textContent`.** All data från API-svar — action-args,
  audit-detaljer, kommentartext, projektnamn — sätts via `el.textContent`.
  Enda undantaget är `<pre>` med `JSON.stringify` (garanterat escaped av JS).
- **Admin-routes ska aktivt rensa secrets.** Kod-review av alla admin-endpoints:
  om ett fält heter `*_secret`, `*_token`, `*_key`, `*_password` → inkludera
  aldrig utan explicit whitelist. `test_no_secret_leak.py` är icke-valfritt.
- **`_require_admin` i varje admin-handler.** Inte en middleware — varje handler
  anropar `_require_admin(request, acl)` explicit. Enklare att granska.

### `AuditLog.query()` — förväntat kontrakt

```python
class AuditLog:
    def query(
        self,
        *,
        user: str | None = None,
        project: str | None = None,
        tool: str | None = None,
        ok: bool | None = None,
        since: str | None = None,   # ISO-datum, t.ex. "2026-07-01"
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[dict], int]:
        """Returnera (entries, total_matching).
        entries är lista av {ts, user, project, tool, ok, detail}.
        detail är None eller kort felsträng — aldrig lösenord/secrets/requestbody.
        """
```

Om `query()` ännu inte tar `offset`/`limit` och returnerar `(list, int)`:
uppdatera `safety/audit.py` som en del av Fas C steg 9.

### `pollBadge` och Page Visibility — kontrakt (definierat i `app.js` Fas A)

```js
function pollBadge(path, badgeEl, interval = 10_000) {
  const tick = async () => {
    if (document.visibilityState === 'hidden') return;
    try {
      const data = await api('GET', path);
      const count = data.pending_outbox ?? 0;
      badgeEl.textContent = count > 0 ? count : '';
      badgeEl.hidden = count === 0;
    } catch (_) { /* nätverksfel — visa inget */ }
  };
  const id = setInterval(tick, interval);
  document.addEventListener('visibilitychange', tick);
  tick();
  return {
    stop: () => {
      clearInterval(id);
      document.removeEventListener('visibilitychange', tick);
    }
  };
}
```

Utkorgssidens lokala poll (för listvyn) implementeras analogt men anropar
`api_outbox_list` och kör `reconcileOutboxList`.

### Filstruktur (Fas C — tillägg till Fas A+B)

```
gateway/src/memaix_gateway/
└── web/
    ├── api/
    │   ├── outbox.py         (NYTT Fas C)
    │   ├── board_card.py     (NYTT Fas C — kortmodal + kommentarer + score)
    │   └── admin.py          (NYTT Fas C)
    ├── pages/
    │   ├── outbox.html       (NYTT Fas C)
    │   └── admin.html        (NYTT Fas C)
    └── static/
        ├── outbox.js         (NYTT Fas C)
        ├── board.js          (UPPDATERAS Fas C — kortmodal + deep-link + drag-lock)
        └── admin.js          (NYTT Fas C)
```

`web/routes.py` utökas med Fas C-routes. Inga existerande routes ändras.

---

## 8. Acceptanskriterier

**Utkorg:**

- [ ] Utkorg-badge i sidebar visar antal väntande; poll pausar när tabben är dold.
- [ ] `/app/outbox` listar väntande ärenden för alla synliga projekt; projektfilter
      avgränsar listan korrekt.
- [ ] Reader ser listan och kan förhandsgranska men saknar Godkänn/Avvisa-knappar
      (client-side dolt och server-side 403 om POST försöks direkt).
- [ ] Owner godkänner ett `email_send`-ärende → verktyget utförs exakt en gång;
      rad uppdateras till `executed`.
- [ ] Dubbel-godkännande (race condition) → 409, toast "Redan avgjort av {user}",
      rad uppdateras med korrekt status utan sidladdning.
- [ ] Avvisning med orsak → status `rejected`, orsak synlig i preview-modal.
- [ ] Förfallna ärenden (`expired`) kan inte godkännas (status-maskin 409).
- [ ] Preview-modal visar strukturerad rendering (Till/Ämne för email, Händelse/Tid
      för kalender); ingen rå JSON för vanliga verktygstyper.

**Kortmodal:**

- [ ] Klick på korttitel öppnar modal med kortdetalj, kommentarslista och V/C/R-steppers.
- [ ] URL uppdateras med `?item=BL-X`; stäng modal → URL återställs.
- [ ] `?item=BL-X` i direktlänk öppnar modalen automatiskt vid sidladdning.
- [ ] V/C/R-stepper med snabb klickning skickar ett enda PATCH-anrop (800ms debounce).
- [ ] Collaborator kan kommentera och poängsätta; kommentaren visas direkt.
- [ ] Reader ser V/C/R och kommentarer; stepper och formulär är inaktiva med
      förklarande text "Kräver collaborator-roll".

**Admin:**

- [ ] `/app/admin` returnerar 403 för icke-admin; länken syns inte i sidebaren.
- [ ] Flik Användare: alla användare × projekt visas som grants-matris med rätt
      roll-chips.
- [ ] Flik Projekt: expand-rad visar konfiguration; `allow_send` och `outbox_mode`
      visas korrekt.
- [ ] Flik Audit: filtrering på `user`, `project`, `tool`, `ok` och `since` fungerar;
      felade rader expanderbara med detail-text i mono-typsnitt.
- [ ] "Visa fler" appender nästa 50 poster utan att töma listan.
- [ ] Flik System: hälsostatus visas med rätt ikon och färg; OAuth-sektion innehåller
      aldrig secrets (`test_no_secret_leak.py` är grön).
- [ ] Full testsvit grön: `python -m pytest -q` från `gateway/`.
- [ ] Docs-index grön: `python3 scripts/check-docs-index.py`.
