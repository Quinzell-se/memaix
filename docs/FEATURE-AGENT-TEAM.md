# Agent-teamet — flera agenter som ett lag runt boarden (design + byggspec)

Funktion #11. Vänder memaix ensamma agentloop (FEATURE-LLM-ENGINE fas 2) till ett
**koordinerat team**: en PM-agent bryter ett mål i länkade tasks och tilldelar dem,
specialistagenter plockar upp sina tasks, gör jobbet, skriver en handoff nästa agent
läser — och boarden är den delade sanningen som gör dem till ett lag i stället för
fyra främlingar.

## Insikten: teamet finns redan, det är inte hopkopplat
Nästan allt finns i produktion. Detta är ihopkoppling, inte ny grundarkitektur.

| Lagdel | Redan byggt | Gap att täcka |
|---|---|---|
| Kanban-board | `board/` + `/app/board` (store, UI, kort) | visa `assignee` på kort |
| Planering + länkade tasks | `pm_plan_sprint`, `dependency_add`, `milestone_add`, backlog inbox→done | PM-agent som *tilldelar* |
| Rätt agent till rätt task | RBAC + projektroller (agenter = användare) | agent-identiteter seedas |
| Agenter som utför | LLM-motorn fas 2 (loop, brygga, budget) | köra headless per identitet |
| Handoff nästa agent läser | vault + minnestrappan (fas B) | handoff-konvention i prompt |
| Autonom drift | brief-schemaläggaren (asyncio-loop) | läge B: upplockar-loop |
| Mobil/Telegram | notify- + connector-lagret | (finns — ingen ny kod) |

**Kontext-brännproblemet är redan löst.** En backend-agent som improviserar och bränner
sitt fönster på att minnas "vilka tabeller finns" är exakt vad **minnestrappan** botar:
agenten *konsulterar* verifierat minne i stället för att bära det. Förmåge-registret är
den pålitliga vägen (inga improviserade verktyg); trappan är det persistenta tillståndet.
Samma roll som en "agent-native backend" fyller — men leverantörsoberoende.

## Rollmodell — team = RBAC, inte ny mekanism
Varje agent är en **användare i acl.yaml** med minsta möjliga roll (SAFETY.md gäller
oförändrat — teamet försvagar aldrig RBAC/outbox/audit):

| Agent | Roll (per projekt) | Ser (rollfiltrerad brygga) |
|---|---|---|
| `pm-agent` | owner | planera, tilldela, sätta status |
| `backend-agent` | collaborator | minne, backlog, filer, kod-verktyg |
| `frontend-agent` | collaborator | minne, backlog, filer |
| `tester-agent` | reader (+ backlog-kommentar) | läsa allt, rapportera — kan inte skriva prod |

Rollfiltret i verktygsbryggan (fas 2) ger detta gratis: en tester-agent *ser* inte
skriv-verktyg. Least privilege per agent, precis som externa personer.

## Datamodell — ett fält, inte en ny tabell
Backlog-item (frontmatter idag: id, author, category, status, value, complexity) får:
- **`assignee`** — agent-/användarnamn, eller tomt (ingen). PM sätter det.
- **`handoff`** — sökväg till vault-noteringen som avslutande agent skrev (eller inbäddad
  i item-kroppen under `## Handoff`). Nästa agent läser den FÖRST.

Boardens `_card_view` (board/store.py) exponerar `assignee` så mobilkortet visar vem som
äger raden. En "Mina tasks"-vy = filter på assignee. Ingen schemamigrering — markdown-
frontmatter är additivt.

## Handoff-konventionen (det som gör dem till ett team)
Nyckelinsikten ur förebilden: *nästa agent läser summeringen innan den börjar.* Konkret:
1. När en agent sätter en task till nästa status skriver den en handoff-notering till
   vaulten: vad som byggdes, vad nästa agent behöver veta (API-form, filnamn, beslut).
   Status **hypotes** tills verifierad (trappan) — en obekräftad handoff får inte läsas
   som faktum.
2. `assignee` flyttas till nästa agent (PM:en eller en statusregel avgör vem).
3. Nästa agents systemprompt injicerar: "Läs handoff-noteringen för din task FÖRE allt
   annat. Anta inget den inte säger — fråga PM-agenten via en backlog-kommentar."

Boarden bär planen; vaulten bär kunskapen; trappan skiljer bekräftat från antaget.

## Nya verktyg (tunna — bygger på befintliga)
- `backlog_assign(project, id, assignee, expected_version)` — owner/PM sätter assignee,
  audit-loggat, optimistisk versionslåsning (samma mönster som `backlog_set_status`).
- `team_my_tasks(project)` — backlog filtrerat på anropande identitet + given status.
- `team_handoff(project, id, summary)` — skriver handoff-notering (hypotes) och länkar
  den på itemet. Bekvämlighet ovanpå `memory_write` + `backlog_comment`.

## Läge B — den autonoma upplockar-loopen (PM-AGENT.md)
En schemalagd server-loop (brief-schemaläggarens mönster, som destillatrutinen i
SELF-IMPROVING fas C) per agent-identitet:
```
för varje agent-identitet med autonomi på:
  tasks = team_my_tasks(projekt, status="assigned till mig")
  för varje task (nyaste först, en i taget):
    läs handoff + item → run_turn(agent, "utför denna task") [LLM-motorn fas 2]
    skriv handoff → flytta assignee/status → audit
```
**Bunden autonomi (obligatorisk, PM-AGENT §Bounded autonomy):** per-agent dygnsbudget
(DailyBudget finns), max tasks per körning, loop-detektion (samma task två varv utan
statusändring → pausa + notis), och en **människa-i-loopen-grind** på det som når
outboxen (utgående/destruktivt kräver bekräftelse — teamet kan planera och koda fritt,
men inte mejla/radera utan människa).

## Faser (en PR per fas, CI + oberoende granskning för auth/ACL-delar)
**Fas 1 — assignee + board.** `assignee` i backlog-schemat, `backlog_assign`-verktyg,
kort visar ägare, "Mina tasks"-filter i boarden. Ingen autonomi än — bara synligt vem
som äger vad. ✅ Klar när: PM kan tilldela via verktyg och mobilkortet visar assignee.

**Fas 2 — agent-identiteter + handoff.** Seeda pm/backend/frontend/tester i acl.yaml
(least privilege), `team_my_tasks` + `team_handoff`, handoff-regeln i systemprompten.
✅ Klar när: en manuellt driven agent läser sin handoff, gör en task, skriver nästa.

**Fas 3 — PM-agenten planerar & tilldelar.** En prompt/skill som tar ett mål →
`pm_plan_sprint` + `dependency_add` + `backlog_assign` till rätt roll. Planen går genom
outboxen för mänskligt ok innan teamet sätter igång (första körningen; konfigurerbart).
✅ Klar när: "bygg X" → länkade tilldelade tasks på boarden, godkända av en människa.

**Fas 4 — läge B, autonom drift.** Upplockar-loopen med budgetar/loop-detektion/audit;
notiser (Telegram/notify) när en task byter hand eller fastnar. ✅ Klar när: ett godkänt
mål driver sig självt task för task, en människa ser raderna röra sig i mobilen och kan
avbryta.

## Vad vi INTE gör (bindande)
- **Ingen försvagad RBAC/outbox/audit** i teamets namn — varje agent är least-privilege,
  utgående går genom outboxen, allt loggas med agent-identitet.
- **Ingen obegränsad autonomi** — budget, task-tak och loop-detektion är krav, inte
  finish (PM-AGENT.md).
- **Ingen självtilldelning av privilegier** — en agent kan inte höja sin egen roll; bara
  en människa (admin) ändrar acl.yaml-roller.
- **Handoffs börjar som hypotes** — en agent bygger inte vidare på en obekräftad handoff
  som om den vore faktum (minnestrappan).

## Beroenden
Fas 1 fristående. Fas 2 kräver LLM-motorn fas 2 (klar) + minnestrappan (klar). Fas 3
kräver fas 2. Fas 4 kräver fas 3 + brief-schemaläggarens loop-mönster (finns). Delar
självförbättrande systemets väktare för hälsa och SELF-IMPROVING fas D:s eval-svit för
regression på teamets beteende.
