# Säkerhet & kända fallgropar

## Hårda regler
- **OAuth via ory Hydra, ingen Access framför.** Auth hanteras av **ory Hydra** (certifierad
  OAuth2/DCR), inte hemsnickrad kod — gateway validerar tokens. Lägg **inte** Cloudflare Access
  "Managed OAuth" MCP-portal framför endpointen — dokumenterad bugg där claude.ai **webb + mobil**
  misslyckas med OAuth medan desktop funkar mot samma URL. Tunneln ska vara en ren proxy.
  *(v2 — se `REVIEW-RESPONSE.md`.)*
- **Stäng av Bot Fight Mode / "Block AI training bots"** för MCP-hostnamnet, annars blockerar
  Cloudflare AI-leverantörens anrop.
- **Backend-credentials serverside.** Lösenord (IMAP/SMTP, WebDAV) ligger i `.env`, refereras via
  `*_ref` i acl.yaml, och exponeras aldrig mot AI:n.
- **`allow_send: false` som default.** AI:n skapar utkast; människan skickar.
- **Minst privilegium.** Externa medarbetare = exakt ett projekt. Verifiera isoleringen efter
  varje ACL-ändring.

## Exponeringsyta
- Endast `mcp.<domän>` ska vara publik. Gatewayens port bindas till localhost; tunnel/proxy
  hanterar inkommande.
- Logga verktygsanrop per användare + projekt (`features.audit_log: true`).

## Supply chain (publik repo + många beroenden)
Hydra, Nextcloud, Ollama, Python-libs och base-images = stor attackyta, särskilt med öppen kod.
- **Pinna beroenden** (versioner + hashar), generera **SBOM**, **image-scanning** i CI, och
  **signera releaser**. (OPEN-GAPS #5)

## AI-specifika hot
Prompt injection och exfiltrering (en AI som läser fientligt mejl/innehåll) hanteras separat i
**[THREAT-MODEL.md](THREAT-MODEL.md)** — den största säkerhetsluckan; läs den.

## Granska alltid
Memaix låter en AI agera på riktig data. Granska utkast och åtgärder innan de skickas eller
publiceras. `email_send` och andra skrivåtgärder bör ha mänsklig bekräftelse tills du litar på
flödet.
