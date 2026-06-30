# White-label — kör Memaix under eget namn

Memaix är byggt för att kunna levereras under en kunds eget varumärke. Allt användarvänt namn
läses från `config/brand.yaml` — koden hårdkodar aldrig produktnamnet.

## Vad som byts
- `name` — visas i OAuth-consent-skärmen, loggar, e-postavsändarnamn.
- `tagline`, `support_email`, `primary_color`, `logo_path`.

## Vad kunden styr själv
- **Eget namn** — `brand.yaml`.
- **Egen installation** — kunden (eller du som leverantör) kör en egen instans.
- **Egna domäner** — `memaix.yaml: server.public_url` + `tunnel.hostname`.
- **Egna tunnlar** — egen Cloudflare-tunnel eller egen reverse proxy.

## Checklista vid white-label-leverans
1. Sätt `brand.yaml` till kundens namn/branding.
2. Sätt kundens domän i `memaix.yaml` och koppla deras tunnel.
3. Initiera deras projekt + användare i `acl.yaml`.
4. Verifiera att OAuth-consent visar kundens namn, inte "Memaix".

> AGPL-kravet kvarstår även white-labelat: om kunden får tillgång till en modifierad nättjänst
> ska källkoden (med dina ändringar) vara tillgänglig. Branding via config räknas inte som en
> dold modifikation — det är en avsedd funktion.
