# Funktion #6 — Upptäckbarhet: guide & förmåge-register

SPDX-License-Identifier: AGPL-3.0-or-later

Designdok + byggspec för hur användaren guidas och informeras om vad Memaix kan
göra. I Memaix *är* gränssnittet en dialog, så upptäckbarhet är dialogbaserad och
kontextmedveten — men den vilar på ett **maskinläsbart förmåge-register** så att
guidningen förblir korrekt när fler funktioner byggs (brief, sökning, utkorg,
regler, ångra …).

Fyra lager: **L0** register (källa till sanning) · **L1** guidad tur efter
onboarding · **L2** återkommande överbliks-prompt med borra-ner · **L3**
kontextuella knuffar. Byggs stegvis enligt [Byggordning](#byggordning) och
[Utvecklingsinstruktioner](#utvecklingsinstruktioner).

Kompletterar `assistant-manual.md` (styr sessionsstart) och onboarding-intervjun
(bygger profilen) — den här funktionen tillför *"så här använder du mig"*, vilket
saknas idag (OPEN-GAPS #11).

---

## 1. Vad användaren upplever

- **Efter onboarding:** *"Utifrån att du är projektledare på Acme kan jag ta det
  här av dig — vill du prova något nu?"* med 3–4 konkreta ingångar valda utifrån
  profilen och användarens projekt/roller.
- **När som helst:** *"vad kan du göra?"* → en gruppindelad överblick (5–7
  utfallsområden), där varje område kan borras ner: **överblick → område →
  konkret åtgärd → "vill du att jag gör det nu?"**.
- **Mitt i arbetet:** *"Jag sparade utkastet — vill du att jag lägger en
  påminnelse i kalendern?"* — sällan och aldrig påträngande.

Grundprincip: användare tänker i **jobb-att-göra-klart**, inte i verktyg. Allt
grupperas i utfall (*hålla koll på mejl, planera projekt, komma ihåg saker,
morgonbrief*), aldrig som en rå verktygslista. Bara det användaren faktiskt kan
göra (roll, projekt, länkade konton) visas.

---

## 2. Nyckelbeslut

1. **Ett förmåge-register som källa till sanning (L0).** Varje funktion
   registrerar sina förmågor deklarativt. Onboarding-turen, `memaix_help`,
   board-panelen och knuffarna byggs alla ur registret — ni underhåller *en*
   lista, inte fem ytor. **Detta är det som gör upptäckbarheten skalbar.**
2. **Anti-drift som CI-krav.** Ett test verifierar att varje registrerat
   MCP-verktyg tillhör minst en förmåga (eller är uttryckligen märkt internt).
   Lägger man en funktion utan att registrera den → CI faller.
3. **ACL- och konto-medveten filtrering.** Registret filtreras per användare:
   roll-tröskel, resurs (mailbox/kalender/vault) och länkade konton. Föreslå att
   *länka* en saknad förutsättning istället för att visa en död funktion.
4. **AI-agnostiskt.** Allt via MCP-prompt/-resource/-verktyg + manualen — ingen
   klient-specifik UI. Fungerar i Claude, ChatGPT m.fl.
5. **Fråga-först & lokaliserat.** Tur och knuffar är opt-in (som intervjun) och
   all text går via i18n.

---

## 3. Översikt

```
  capabilities/registry.py   ← varje funktion lägger CAPABILITY-poster (L0)
        │
        │  available_for(acl, user, accounts, cfg)  → ACL/konto/resurs-filtrerat
        ├───────────────► L1  onboarding-tur     (efter complete_onboarding)
        ├───────────────► L2  memaix_help / capabilities  (överblik → drill-down)
        ├───────────────► L3  nudges.suggest(last_tool, ctx)  (kontextuell knuff)
        └───────────────► board  GET /board/api/capabilities  (panel)
```

---

## 4. Förmåge-modell (L0)

`capabilities/registry.py` — deklarativa poster. Ingen DB; en modul-lista som
funktioner utökar (importeras vid uppstart).

```python
@dataclass(frozen=True)
class Capability:
    key: str                 # 'memory.remember'
    area: str                # 'memory' | 'mail' | 'calendar' | 'backlog' |
                             # 'pm' | 'brief' | 'search' | 'automation' | 'undo'
    title_key: str           # i18n-nyckel, t.ex. 'cap.memory.remember.title'
    summary_key: str         # i18n-nyckel
    tools: tuple[str, ...]   # MCP-verktyg posten täcker ('memory_write', ...)
    example_prompts_key: str # i18n-nyckel → lista av exempelprompter
    needs_role: str = 'reader'          # min-roll i något projekt
    needs_resource: str | None = None   # 'mailbox'|'calendar'|'vault'|None
    needs_account: str | None = None     # 'google'|'microsoft'|None
    tags: tuple[str, ...] = ()          # för profil-matchning i turen

AREAS = ('memory','mail','calendar','backlog','pm','brief','search','automation','undo')

REGISTRY: list[Capability] = []
def register(*caps: Capability) -> None: REGISTRY.extend(caps)
def all_capabilities() -> list[Capability]: ...
```

Filtrering:

```python
def available_for(acl, user, accounts: list[dict], cfg) -> list[Capability]:
    """Returnera de förmågor användaren faktiskt kan använda nu.

    En förmåga tas med om användaren i NÅGOT synligt projekt har >= needs_role
    OCH (needs_resource is None eller resursen finns i det projektet) OCH
    (needs_account is None eller kontot är länkat). Annars klassas den som
    'locked' med en anledning ('link_google'/'no_mailbox'/…) för uppmaning.
    """
```

Registret fylls av respektive tool-modul (eller en central `capabilities/catalog.py`
som importerar allt). Exempel:

```python
register(
    Capability('memory.remember', 'memory', 'cap.memory.remember.title',
               'cap.memory.remember.summary', ('memory_write','memory_append'),
               'cap.memory.remember.examples', needs_role='collaborator',
               needs_resource='vault', tags=('minne','anteckning')),
    Capability('mail.triage', 'mail', 'cap.mail.triage.title',
               'cap.mail.triage.summary', ('email_list','email_search','email_read'),
               'cap.mail.triage.examples', needs_role='collaborator',
               needs_resource='mailbox', tags=('mejl','inkorg')),
    # … brief/search/outbox/rules/undo registrerar sina egna när de byggs
)
```

---

## 5. L1 — Guidad tur efter onboarding

Utöka onboarding (`tools/onboarding.py`). Efter `complete_onboarding`:

```python
def build_tour(user, profile_text, available: list[Capability],
               t, max_items=4) -> dict:
    """Returnera {greeting, suggestions:[{title, why, example, tool}], areas:[...]}.

    Rangordna 'available' mot profilen: matcha Capability.tags mot ord i
    profil-texten (roll, ansvar, mål). Faller tillbaka på en standarduppsättning
    (minne, mail, backlog, brief) om inget matchar. Lokalisera via t().
    """
```

`complete_onboarding(...)` returnerar nu även `tour = build_tour(...)`. En MCP-
prompt `onboarding_tour` (eller ett tillägg i den befintliga `onboarding_interview`-
avslutningen) presenterar turen: kort hälsning, 3–4 *"vill du prova?"*-ingångar,
och en enradersöversikt av övriga områden att fråga om senare. Turen ska *göra*
(erbjuda att köra en åtgärd), inte bara berätta.

---

## 6. L2 — Överblik & drill-down

Verktyg + prompt i `server.py`:

| Yta | Signatur | Beskrivning |
|-----|----------|-------------|
| verktyg `capabilities` | `(area: str\|None=None)` | Strukturerad, ACL/konto-filtrerad lista. `area=None` → grupperad överblick (områden + korta summeringar + låsta med anledning). `area='mail'` → förmågor i området med exempelprompter. |
| prompt `memaix_help` | `(area: str="")` | Presentationsinstruktion till modellen: rendera överblick → låt användaren välja område → visa åtgärder → erbjud *"vill du att jag gör det nu?"*. Använder `capabilities` som data. |
| resource `memaix://capabilities` | — | Samma data som resource, för klienter som läser resurser vid sessionsstart. |

Överblicken håller toppnivån kort (5–7 områden). Låsta förmågor visas med
uppmaning (*"Koppla din Google-kalender för att låsa upp kalenderfunktioner —
kör `account_link('google')`"*).

---

## 7. L3 — Kontextuella knuffar

`capabilities/nudges.py` — lätt och sällan:

```python
def suggest(user, last_tool: str, available: list[Capability],
            store, *, now, min_gap_h=6) -> dict | None:
    """Returnera {text_key, capability_key} eller None.

    Enkel regel-tabell: föregående verktyg → föreslagen nästa förmåga
    (t.ex. email_create_draft → 'calendar.remind', backlog_add → 'pm.plan',
    upprepat mönster → 'automation.rule'). Filtrera mot 'available'. Tysta om
    en knuff gavs för < min_gap_h sedan (spårat per user i en liten tabell,
    återanvänd notify/state-DB)."""
```

Exponeras som ett litet verktyg `next_suggestion(last_tool)` som modellen *kan*
kalla, och beskrivs i `assistant-manual.md` så assistenten väver in det naturligt
och sparsamt. Aldrig mer än en knuff per interaktion; opt-out via inställning.

---

## 8. Board & first-run

- **Board-panel:** `GET /board/api/capabilities` (ACL-filtrerat via cookie-
  användaren) → en "Vad kan jag göra?"-vy grupperad per område, med
  exempelprompter att kopiera. För dem som hellre skummar än frågar.
- **First-run-exempel:** `example_prompts` per förmåga (i18n) dubblar som
  startprompter; visa några på board:ens tomma tillstånd.

---

## 9. Anti-drift (det viktigaste)

Ett test (`tests/test_capabilities_coverage.py`) som:
1. Räknar upp alla registrerade MCP-verktyg (introspektera `mcp` / en
   `TOOL_NAMES`-lista i `server.py`).
2. Räknar upp alla `tools` i `REGISTRY` + en explicit `INTERNAL_TOOLS`-mängd
   (t.ex. `whoami`, `capabilities`, `memaix_help`, `onboarding_complete`).
3. **Failar** om något verktyg varken är täckt av en förmåga eller markerat
   internt.

Det gör registret till en kontrakts-yta: en ny funktion är inte "klar" förrän den
är upptäckbar. Kombinera med en rad i varje funktions acceptanskriterier:
"registrerad i capabilities + i18n-nycklar + coverage-testet grönt".

---

## 10. Säkerhet & integritet

- **Filtrering läcker inte.** `available_for` avslöjar bara förmågor användaren
  får använda; låsta visas som *kategori* + uppmaning, aldrig med projekt-/
  kontodetaljer användaren inte har åtkomst till.
- **Board-panelen** använder samma cookie-auth + `visible_projects` som övriga
  board-API:er.
- **Knuffar** loggas inte med innehåll; bara att en knuff gavs (för min_gap).
- **Ingen PII i registret** — bara i18n-nycklar och verktygsnamn.

---

## Byggordning

1. **Registret** (`capabilities/registry.py`) — `Capability`, `register`,
   `all_capabilities`, `available_for`. *Isolerat testbart.*
2. **Katalog** (`capabilities/catalog.py`) — registrera nuvarande förmågor
   (memory/mail/calendar/backlog/pm). i18n-nycklar.
3. **Coverage-test** — anti-drift (§9). Fixa luckor.
4. **L2** — `capabilities`-verktyg + `memaix_help`-prompt + resource.
5. **L1** — `build_tour` + tur i onboarding-avslutningen.
6. **L3** — `nudges.suggest` + `next_suggestion`-verktyg + manual-text.
7. **Board** — `/board/api/capabilities` + panel.
8. **i18n + docs.**
9. **CI** — grönt.

---

## Utvecklingsinstruktioner

Konventioner: se funktion #1-doket. Kör `python -m pytest -q` från `gateway/`.

### Steg 1 — `capabilities/registry.py`
Paket `capabilities/__init__.py` + `Capability`-dataclass, `REGISTRY`,
`register`, `all_capabilities`, `available_for(acl, user, accounts, cfg)`.
`available_for` returnerar två listor eller taggar poster `available`/`locked`
med `lock_reason`. **Test** (`tests/test_capabilities_registry.py`): reader ser
inte `needs_role='collaborator'`-förmåga; förmåga med `needs_resource='mailbox'`
låst om projektet saknar mailbox; `needs_account='google'` låst utan länkat
konto; grupperingen täcker rätt områden.

### Steg 2 — `capabilities/catalog.py`
Registrera dagens förmågor (memory, mail, calendar, backlog, pm) med
i18n-nycklar och `example_prompts_key`. Importeras från `server.py` vid uppstart.
Lägg nycklarna i `i18n/locales/en.json` + `sv.json` (övriga får fallback).
**Test:** `all_capabilities()` innehåller minst en post per icke-tom area;
alla `title_key`/`summary_key` finns i `en.json`.

### Steg 3 — Coverage-test (anti-drift)
`tests/test_capabilities_coverage.py` enligt §9. Definiera `INTERNAL_TOOLS` i
`capabilities/catalog.py`. Introspektera verktygsnamnen (lägg vid behov en
`TOOL_NAMES: set[str]` i `server.py` som fylls av `@mcp.tool()`-registreringen
eller hårdlista + ett test som kollar mot `mcp`). **Test:** failar om ett verktyg
saknar täckning. Kör och fixa ev. luckor nu.

### Steg 4 — L2 (`server.py`)
`_get_accounts(user)` (via token_store). Verktyg `capabilities(area=None)` som
kör `available_for` och grupperar; prompt `memaix_help(area="")`; resource
`memaix://capabilities`. Rendera texter via `i18n` (locale från config/where
möjligt). **Test** (`tests/test_server.py`): `capabilities()` för en reader döljer
collaborator-förmågor och listar låsta med anledning; `capabilities('mail')`
returnerar exempelprompter.

### Steg 5 — L1 (tur)
`tools/onboarding.py`: `build_tour(user, profile_text, available, t, max_items=4)`
med tag-matchning mot profiltexten. `complete_onboarding` returnerar `tour`.
Prompt `onboarding_tour`. **Test** (`tests/test_onboarding.py`): profil som nämner
"projektledare" rankar pm/backlog-förmågor högt; tom profil ger standarduppsättning;
turen innehåller körbara exempel.

### Steg 6 — L3 (knuffar)
`capabilities/nudges.py`: `suggest(...)` + regel-tabell + min_gap via en liten
tabell (återanvänd `MEMAIX_STATE_DB`/notify-store). Verktyg `next_suggestion(last_tool)`.
Lägg en rad i `assistant-manual.md` om sparsam användning. **Test**
(`tests/test_nudges.py`): draft → föreslår kalender-påminnelse; knuff tystas inom
min_gap; låst förmåga föreslås aldrig.

### Steg 7 — Board
`GET /board/api/capabilities` (cookie-auth, ACL-filtrerat) + "Vad kan jag göra?"-
panel i `board.html`; exempelprompter i tomt tillstånd. **Test:** route returnerar
filtrerad lista för inloggad användare; ej autentiserad → 401.

### Steg 8 — i18n + docs
Fyll `cap.*`-nycklar i `en.json`/`sv.json`. Registrera doket i `docs/INDEX.md`
(gjort). Lägg en rad i `assistant-manual.md`: *"Vid 'vad kan du göra?' — kör
`capabilities` och presentera överblick → drill-down; erbjud att utföra."*

### Steg 9 — Kör allt
`cd gateway && python -m pytest -q` + `python3 scripts/check-docs-index.py`.

### Acceptanskriterier
- [ ] `capabilities()` ger en gruppindelad, ACL/konto-filtrerad överblick; `capabilities('mail')` borrar ner med exempelprompter.
- [ ] `memaix_help` presenterar överblick → drill-down → *"vill du att jag gör det nu?"*.
- [ ] Efter onboarding får användaren en profil-anpassad tur med 3–4 körbara ingångar.
- [ ] Låsta förmågor visas som kategori + uppmaning (t.ex. länka konto), aldrig med detaljer användaren saknar åtkomst till.
- [ ] Coverage-testet failar om ett MCP-verktyg varken är i registret eller `INTERNAL_TOOLS` — bevisat genom att tillfälligt ta bort en post.
- [ ] Kontextuell knuff ges sparsamt (min_gap) och aldrig för en låst förmåga.
- [ ] Board-panelen listar bara det inloggad användare kan göra; allt lokaliserat; hela sviten + docs-index grön.

---

## Framtida arbete
- Naturspråks-sök i förmågor ("kan du hjälpa mig med fakturor?") via funktion #2.
- Användningsstatistik → föreslå oanvända men relevanta förmågor.
- Interaktiv "tour mode" som steg-för-steg låter användaren prova varje område.
- Auto-genererade exempelprompter per bransch/roll (koppla till mallar/kallstart).
- Achievement-/progress-känsla ("du har provat 4 av 8 områden").
