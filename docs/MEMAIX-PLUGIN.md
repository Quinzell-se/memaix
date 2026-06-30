# Memaix Claude-plugin — konkret innehåll & automation

Det integrerade paketet för Claude-användare (`PACKAGING.md`). Plus svaret på "automatiserar vi med
en hook?" — ja, men hooks är *ett* lager av tre, och inte det viktigaste.

## Layout
```
memaix-plugin/
  .claude-plugin/plugin.json
  skills/
    pm/SKILL.md            # läs projektstatus → planera → presentera (PM-AGENT.md)
    onboarding/SKILL.md     # intervju → fyll om-<person>.md
    brief/SKILL.md          # morgonbrief / dagsavslut
  commands/                 # slash-kommandon (en .md per kommando)
    brief.md plan-sprint.md standup.md whatif.md onboard.md status.md
  agents/
    pm-agent.md             # PM-sub-agenten
  hooks/
    session-start.sh pre-tool-use.sh stop.sh
  references/               # mallar (sprintplan, roadmap, RAID…)
```

## plugin.json (skiss — verifiera mot aktuell plugin-spec vid bygge)
```json
{
  "name": "memaix",
  "version": "0.1.0",
  "description": "Team-gemensamt minne + projektledaragent. Hjärnan minns, agenten agerar.",
  "connectors": [{ "name": "memaix", "url": "https://DIN-INSTANS/mcp" }],
  "skills": ["pm", "onboarding", "brief"],
  "commands": ["brief", "plan-sprint", "standup", "whatif", "onboard", "status"],
  "agents": ["pm-agent"],
  "hooks": { "SessionStart": "hooks/session-start.sh",
             "PreToolUse": "hooks/pre-tool-use.sh",
             "Stop": "hooks/stop.sh" }
}
```

## Slash-kommandon (appkänslan)
| Kommando | Gör |
|---|---|
| `/memaix:brief` | Morgonbrief: inkorg + kalender + öppna beslut, prioriterat |
| `/memaix:plan-sprint` | Planera en sprint ur backloggen (kapacitet) |
| `/memaix:standup` | Sammanfatta läge + blockerare |
| `/memaix:whatif` | Konsekvensanalys av en ändring (kritisk linje/milstolpe) |
| `/memaix:onboard` | Kör onboarding-intervjun för en ny person |
| `/memaix:status` | Statusrapport per projekt (publik: team/ledning) |

## Automation — tre lager (svaret på "med en hook?")

**Hooks är klient-sidiga, sessions­nivå, Claude-specifika.** De är *ett* lager. De viktiga sakerna
ligger server-side. Tre lager:

**1. Server-side (gateway) — den riktiga gränsen.** RBAC, rate-limiting, destruktiv-bekräftelse,
draft-only, async git-snapshot, audit. **AI-agnostiskt och kan inte kringgås** av en annan klient.
(`SAFETY.md`) — detta är *enforcement*, inte hooks.

**2. Schemalagt (cron → agentloop) — kör utan att någon är inne.** Morgonbrief, deadline-vakt, nattlig
statusrapport. (`PM-AGENT.md` läge B.) En session-hook kan inte göra detta — det måste vara cron på
qronkclawd.

**3. Client-side hooks (i pluginet) — sessionsbekvämlighet.**
- **SessionStart** → ladda operating manual + aktuellt projekts kontext **automatiskt** (deterministiskt,
  inte beroende av att modellen kommer ihåg att läsa `shared/`).
- **PreToolUse** → deterministisk grind (extra bekräftelse innan destruktivt) — *komplement* till
  serverns enforcement, inte ersättning.
- **Stop** → skriv dagsavslut-notering automatiskt i projektets minne.

## Viktigt: lägg inte det viktiga BARA i hooks
Hooks finns bara i klienter som stödjer dem (Claude), och kan kringgås av en annan klient. Eftersom
Memaix är AI-agnostiskt **måste** enforcement vara server-side (gateway) och schemalagt vara cron.
Hooks **förgyller** Claude-upplevelsen — de är inte säkerhetsgränsen och inte den enda automationen.

## Rekommendation
- **Plugin för Claude:** ja — med **SessionStart**-hook (auto-kontext) och **Stop**-hook (dagsavslut).
- **Men:** RBAC/safety/audit i **gateway**, schemalagda rytmer i **cron** — så automationen funkar för
  *alla* AI:er och kör **obevakat**, oberoende av om en Claude-session är öppen.

## Acceptanskriterier
- [ ] Ett plugin installerar connector + skills + slash-kommandon + PM-agent i Claude.
- [ ] SessionStart-hook laddar projektkontext deterministiskt; Stop-hook skriver dagsavslut.
- [ ] Säkerhets-enforcement ligger i gateway (server-side), inte i hooks.
- [ ] Schemalagda rytmer körs av cron/agentloop utan öppen session.
- [ ] Icke-Claude-AI:er får samma kärnautomation (gateway + cron), bara utan hooks-förgyllningen.
