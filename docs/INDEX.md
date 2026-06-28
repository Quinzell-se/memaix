# Memaix-dokumentation — börja här

Läs i den ordning som passar din roll.

## 🧭 Är du beslutsfattare / vill förstå värdet?
1. [PRODUCT.md](PRODUCT.md) — vad det är, problem som löses, use cases, 5 branscher, pitch.
2. [FOR-LEDNINGSGRUPPEN.md](FOR-LEDNINGSGRUPPEN.md) — en sida utan teknik: fråga & följ upp projekt.
3. [ADDON-PROJECT-MANAGEMENT.md](ADDON-PROJECT-MANAGEMENT.md) — PM-agenten (agil + vattenfall), affärsvärde.
4. [ENTERPRISE.md](ENTERPRISE.md) — enterprise-tiern: SSO/SCIM, audit, flotthantering.
5. [LEGAL.md](LEGAL.md) — juridik & ansvar: GDPR-roller, DPA, AI som underbiträde (checklista).

## 🏗️ Ska du bygga gatewayen?
1. [ARCHITECTURE.md](ARCHITECTURE.md) — hur delarna hänger ihop.
2. [MCP-API.md](MCP-API.md) — gränssnittskontraktet: vad man kan göra via MCP.
3. [BUILD.md](BUILD.md) — bygg-ordning, moduler, faser för kärnan.
4. [ADDON-PM-BUILD.md](ADDON-PM-BUILD.md) + [MCP-API-PM.md](MCP-API-PM.md) — PM-modulen: bygg-spec + signaturer.
   · [PM-AGENT.md](PM-AGENT.md) — agent-arkitektur & best practice för PM-agenten.
   · [PM-PLANNING-ENGINE.md](PM-PLANNING-ENGINE.md) — planeringsmotor: resurser, allokering, what-if, rapport.
5. [SAFETY.md](SAFETY.md) — drift-säkerhet: rate limit, circuit breaker, concurrency, context, retention.
6. [REVIEW-RESPONSE.md](REVIEW-RESPONSE.md) — v2-justeringar efter oberoende granskning.

## 🚀 Ska du installera och driva?
1. [INSTALL.md](INSTALL.md) — installation (automatisk + manuell).
2. [WIZARD.md](WIZARD.md) — den guidade uppsättningen, steg för steg.
   · [SETUP-UI.md](SETUP-UI.md) — webb-wizard vs native app + säkerhetsdesign.
3. [AUTO-INSTALLER.md](AUTO-INSTALLER.md) — hela planen för det auto-installerande systemet.
   · [DOCTOR.md](DOCTOR.md) — verifiering & hälsokontroll (alla checkar, rapportformat).
   · [OBSERVABILITY.md](OBSERVABILITY.md) — drift-insyn: loggar, metrics, larm.
4. [SECURITY.md](SECURITY.md) — härdning + kända fallgropar (OAuth, Cloudflare).
5. [AI-CLIENTS.md](AI-CLIENTS.md) — koppla in Claude, ChatGPT, Mistral m.fl.
6. [BACKENDS.md](BACKENDS.md) — koppla in Gmail, M365, Nextcloud m.fl. (adaptrar).
7. [PER-USER-OAUTH.md](PER-USER-OAUTH.md) — koppla din egen Gmail/M365 (länkning, token, refresh).
8. [SELF-HOST-STACK.md](SELF-HOST-STACK.md) — topologi (Nextcloud-samlokalisering) + mejl-provisionering.
9. [MAIL.md](MAIL.md) — mejlstrategi: leverantörer, reseller-postur, transaktionsmejl, slutanvändar-UI.
10. [SYSTEM-MAIL.md](SYSTEM-MAIL.md) — systemmejl: config, avsändardomän/DKIM, mallar.
11. [BACKUP.md](BACKUP.md) — backup & återställning (vaults, config, hemligheter, Nextcloud).
12. [UPDATE.md](UPDATE.md) — uppdatering: versionsmigrering, rollback, nedtid.

## 💼 Ska du sälja installation/hosting?
1. [BUSINESS-CASE.md](BUSINESS-CASE.md) — kostnad, pris, kritisk bedömning (publik-OSS-verklighet).
2. [SERVICE-PROVIDERS.md](SERVICE-PROVIDERS.md) — affärsmodellen: en instans per kund, på kundens infra.
3. [WHITE-LABEL.md](WHITE-LABEL.md) — kör under kundens eget namn, domän och tunnel.

## Snabbkarta
| Fråga | Läs |
|---|---|
| Vad är det och varför? | PRODUCT, FOR-LEDNINGSGRUPPEN |
| Vad kan man göra via MCP? | MCP-API, MCP-API-PM |
| Hur byggs det? | ARCHITECTURE, BUILD, ADDON-PM-BUILD |
| Hur bygger man en specialiserad agent (PM)? | PM-AGENT |
| Resursplanering, allokering, konsekvensanalys? | PM-PLANNING-ENGINE |
| Hur installerar/driver jag? | INSTALL, WIZARD, SETUP-UI, AUTO-INSTALLER, SECURITY, AI-CLIENTS |
| Hur verifierar jag installationen? | DOCTOR |
| Kan vi koppla in Gmail/M365 & egna konton? | BACKENDS, PER-USER-OAUTH |
| Self-host: Nextcloud + mejl-provisionering? | SELF-HOST-STACK |
| Mejlstrategi & systemmejl? | MAIL, SYSTEM-MAIL |
| Backup & återställning? | BACKUP |
| Hur uppdaterar jag säkert? | UPDATE |
| Hur tjänar vi pengar? | BUSINESS-CASE, SERVICE-PROVIDERS, WHITE-LABEL, ADDON-PROJECT-MANAGEMENT |
| Kostnad, pris & lönsamhet? | BUSINESS-CASE |
| Vad krävs för storföretag? | ENTERPRISE |
| Skydd mot skenande AI / concurrency? | SAFETY |
| Hur ser jag att en instans är frisk? | OBSERVABILITY, DOCTOR |
| Vad ändrades efter extern granskning? | REVIEW-RESPONSE |
| Juridik, GDPR & ansvar? | LEGAL |
