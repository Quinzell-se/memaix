# Paketering — connector, skill, plugin

Hur Memaix blir **mer integrerat än en rå connector**. De tre ytorna (2026) är lager i en stack:

| Yta | Vad det är | I Memaix |
|---|---|---|
| **MCP-connector** | *Rören* — ger AI:n åtkomst till verktyg/data | gatewayen (har vi) |
| **Skill** | *Instruktionerna* — lär AI:n *hur* en uppgift görs (SKILL.md, kan auto-triggas; slash-kommandon ingår numera i skills) | PM-/onboarding-/brief-skills |
| **Plugin** | *Produkten* — buntar connector + skills + slash-kommandon + sub-agenter till **ett installerbart paket** ("känns som att installera en app") | Memaix-pluginet |

> Connectorn ensam = förmåga utan vägledning. Skill ensam = vägledning utan verktyg. **Pluginet gifter
> ihop dem** + ger slash-kommandon och sub-agenter. Det är "mer integrerat".

## Den layerade strategin för Memaix
1. **Universell kärna:** MCP-connector + verktyg + planeringsmotor. Öppen standard, funkar med *vilken*
   AI som helst. (Detta är fundamentet — byts aldrig ut, bara *wrappas*.)
2. **Portabel upplevelse:** Memaix-egna skills/playbooks (operating manual, PM-playbooks) **lagrade i
   vaulten** och lästa via connectorn → guidat beteende i *vilken* AI (ChatGPT/Mistral) utan
   klient-specifikt plugin.
3. **Per-klient-plugin (polerad integration):** en **Claude-plugin** först (rikast plugin-ekosystem),
   ev. ChatGPT-app senare. Tunna wrappers runt samma connector.

## Vad Memaix Claude-plugin innehåller
```
memaix-plugin/
  .claude-plugin/plugin.json   # namn, beskrivning, connector-referens
  skills/                      # SKILL.md per förmåga (pm, onboarding, morgonbrief, dagsavslut)
  commands/                    # slash-kommandon
  agents/                      # PM-sub-agenten (PM-AGENT.md)
  references/                  # mallar (sprintplan, roadmap, RAID…)
```
**Slash-kommandon = den konkreta "appkänslan":**
`/memaix:brief` · `/memaix:plan-sprint` · `/memaix:standup` · `/memaix:whatif` · `/memaix:onboard` ·
`/memaix:status`. Användaren *triggar* en förmåga istället för att formulera en prompt.

## AI-agnostisk-brasklapp
Plugin-formatet är **Claude-specifikt** (Cowork/Claude-plugins, ChatGPT har Apps SDK). Memaix är
AI-agnostiskt — så:
- **Kärnan (connector + verktyg) förblir universell.**
- **Den portabla skill-packen i vaulten** ger guidat beteende även i icke-Claude-AI:er via connectorn.
- **Plugins är polerade per-klient-wrappers** ovanpå — bygg där det lönar sig (Claude först), inte överallt.

## Rekommendation
**Ja — paketera Memaix som ett plugin, inte bara en connector** — men behåll connectorn + den portabla
skill-packen som AI-agnostisk grund. Då får Claude-användare en app-lik, slash-driven upplevelse, medan
ChatGPT/Mistral-användare ändå får guidat beteende via connectorn.

## Faser
1. **Connector + verktyg** (universell kärna) — *har vi specat*.
2. **Portabel skill-pack i vaulten** (operating manual + PM-playbooks) — guidat i vilken AI som helst.
3. **Claude-plugin** — connector + skills + slash-kommandon + PM-sub-agent (det integrerade paketet).
4. **Andra klienter** (ChatGPT-app m.fl.) vid behov.

## Acceptanskriterier
- [ ] Kärnan (connector/verktyg) fungerar i vilken MCP-AI som helst — oförändrad.
- [ ] En Claude-användare installerar **ett** plugin och får verktyg + skills + slash-kommandon.
- [ ] Slash-kommandon triggar förmågor (`/memaix:brief` osv.) utan att användaren formulerar prompts.
- [ ] Icke-Claude-AI:er får guidat beteende via den portabla skill-packen i vaulten.
