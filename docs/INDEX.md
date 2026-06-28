# Memaix-dokumentation — börja här

Läs i den ordning som passar din roll.

## 🧭 Är du beslutsfattare / vill förstå värdet?
1. [PRODUCT.md](PRODUCT.md) — vad det är, problem som löses, use cases, 5 branscher, pitch.
2. [FOR-LEDNINGSGRUPPEN.md](FOR-LEDNINGSGRUPPEN.md) — en sida utan teknik: fråga & följ upp projekt.
3. [ADDON-PROJECT-MANAGEMENT.md](ADDON-PROJECT-MANAGEMENT.md) — PM-agenten (agil + vattenfall), affärsvärde.

## 🏗️ Ska du bygga gatewayen?
1. [ARCHITECTURE.md](ARCHITECTURE.md) — hur delarna hänger ihop.
2. [MCP-API.md](MCP-API.md) — gränssnittskontraktet: vad man kan göra via MCP.
3. [BUILD.md](BUILD.md) — bygg-ordning, moduler, faser för kärnan.
4. [ADDON-PM-BUILD.md](ADDON-PM-BUILD.md) + [MCP-API-PM.md](MCP-API-PM.md) — PM-modulen: bygg-spec + signaturer.

## 🚀 Ska du installera och driva?
1. [INSTALL.md](INSTALL.md) — installation (automatisk + manuell).
2. [WIZARD.md](WIZARD.md) — den guidade uppsättningen, steg för steg.
   · [SETUP-UI.md](SETUP-UI.md) — webb-wizard vs native app + säkerhetsdesign.
3. [AUTO-INSTALLER.md](AUTO-INSTALLER.md) — hela planen för det auto-installerande systemet.
4. [SECURITY.md](SECURITY.md) — härdning + kända fallgropar (OAuth, Cloudflare).
5. [AI-CLIENTS.md](AI-CLIENTS.md) — koppla in Claude, ChatGPT, Mistral m.fl.
6. [BACKENDS.md](BACKENDS.md) — koppla in Gmail, M365, Nextcloud m.fl. (adaptrar).
7. [PER-USER-OAUTH.md](PER-USER-OAUTH.md) — koppla din egen Gmail/M365 (länkning, token, refresh).
8. [SELF-HOST-STACK.md](SELF-HOST-STACK.md) — topologi (Nextcloud-samlokalisering) + mejl-provisionering.
9. [MAIL.md](MAIL.md) — mejlstrategi: leverantörer, reseller-postur, transaktionsmejl, slutanvändar-UI.
10. [SYSTEM-MAIL.md](SYSTEM-MAIL.md) — systemmejl: config, avsändardomän/DKIM, mallar.

## 💼 Ska du sälja installation/hosting?
1. [SERVICE-PROVIDERS.md](SERVICE-PROVIDERS.md) — affärsmodellen: en instans per kund, på kundens infra.
2. [WHITE-LABEL.md](WHITE-LABEL.md) — kör under kundens eget namn, domän och tunnel.

## Snabbkarta
| Fråga | Läs |
|---|---|
| Vad är det och varför? | PRODUCT, FOR-LEDNINGSGRUPPEN |
| Vad kan man göra via MCP? | MCP-API, MCP-API-PM |
| Hur byggs det? | ARCHITECTURE, BUILD, ADDON-PM-BUILD |
| Hur installerar/driver jag? | INSTALL, AUTO-INSTALLER, SECURITY, AI-CLIENTS |
| Kan vi koppla in Gmail/M365 & egna konton? | BACKENDS, PER-USER-OAUTH |
| Self-host: Nextcloud + mejl-provisionering? | SELF-HOST-STACK |
| Hur tjänar vi pengar? | SERVICE-PROVIDERS, WHITE-LABEL, ADDON-PROJECT-MANAGEMENT |
