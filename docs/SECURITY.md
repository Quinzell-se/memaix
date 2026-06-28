# Säkerhet & kända fallgropar

## Hårda regler
- **Egen OAuth, ingen Access framför.** Memaix är sin egen OAuth 2.1-server (PKCE + CIMD).
  Lägg **inte** Cloudflare Access "Managed OAuth" MCP-portal framför endpointen — det finns en
  dokumenterad bugg där claude.ai **webb + mobil** misslyckas med OAuth medan desktop funkar mot
  samma URL. Tunneln ska vara en ren proxy.
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

## Granska alltid
Memaix låter en AI agera på riktig data. Granska utkast och åtgärder innan de skickas eller
publiceras. `email_send` och andra skrivåtgärder bör ha mänsklig bekräftelse tills du litar på
flödet.
