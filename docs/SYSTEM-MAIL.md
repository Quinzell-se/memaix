# Systemmejl — config, avsändardomän & mallar

Spec för Memaix utgående systemmejl (transaktionsmejl). Bakgrund och leverantörsval: `MAIL.md`.
Pluggbar leverantör → byte är en config-ändring.

## Config (`config/system_mail.yaml`)

```yaml
system_mail:
  provider: ses                       # smtp | ses | mailgun | mailersend
  from: "Memaix <no-reply@notify.example.com>"
  reply_to: "support@example.com"
  sender_domain: "notify.example.com" # egen subdomän för systemmejl (se nedan)
  rate_limit_per_min: 60

  ses:        { region: eu-north-1, access_key_ref: SES_KEY, secret_ref: SES_SECRET }
  mailgun:    { domain: notify.example.com, api_key_ref: MAILGUN_KEY }
  mailersend: { api_key_ref: MAILERSEND_KEY }
  smtp:       { host: smtp.purelymail.com, port: 465, user_ref: SMTP_USER, pass_ref: SMTP_PASS }
```

`*_ref` pekar på `.env`. `provider` väljer vilket block som används; övriga ignoreras.

## Avsändardomän & deliverability (viktigt)

- **Använd en egen subdomän** för systemmejl, t.ex. `notify.<kunddomän>` — **inte** samma domän som
  människors brevlådor. Skyddar brevlådedomänens rykte från att påverkas av systemutskick.
- Sätt **SPF, DKIM, DMARC** på subdomänen. Varje leverantör ger DNS-poster att lägga in:
  - **SES:** verifiera domän-identitet → Easy DKIM (3 CNAME), sätt custom MAIL FROM-subdomän.
  - **Mailgun:** lägg domän → angivna DKIM/SPF/CNAME-poster.
  - **MailerSend:** lägg domän → verifiera DKIM/SPF/Return-Path.
  - **SMTP (Purelymail, dogfooding):** använder Purelymails DKIM för din domän — räcker för låg volym.
- **DMARC** på subdomänen (`p=quarantine` el. `reject` när allt verifierat).

## Mall-uppsättning

Mallarna mappar mot transaktions-användningsfallen i `MAIL.md`.

| Mall | Trigger | Nyckelvariabler |
|---|---|---|
| `invite` | Person får access till projekt | `name, project, role, setup_url` |
| `account_link` | Koppla Gmail/M365 | `name, provider, link_url, expires` |
| `auth_required` | Token utgången | `name, provider, relink_url` |
| `security_alert` | Ny connector / unlink / behörighet | `name, event, when, ip` |
| `verify_email` | Bekräfta adress | `name, verify_url, expires` |
| `report_digest` | Schemalagd rapport (valfri) | `name, period, report_url/body` |
| `operator_alert` | Doctor/backup/cert/kvot (till operatör) | `instance, check, detail` |
| `provisioning_result` | Kundinstallation klar/fel | `customer, status, detail` |
| `billing` | Faktura/förnyelse/trial | `name, amount, due, invoice_url` |

## Rendering & mallfiler

```
templates/email/
  _layout.html.j2        # gemensam ram: brand-logo, färg, footer
  <mall>.md.j2           # brödtext per mall (markdown → HTML + plaintext)
  sv/ · en/              # lokalisering; default en, sv medföljer
```

- **Multipart:** skicka både plaintext och HTML (bättre deliverability, fungerar överallt).
- **Brandning från `brand.yaml`:** `name`, `primary_color`, `logo_path`, `support_email` injiceras i
  `_layout`. White-label utan kodändring.
- **Lokalisering:** välj språk per mottagare (default `en`, `sv` ingår). Lägg fler språkmappar vid behov.

## Notis-kanaler & preferenser
Vart landar morgonbrief, deadline-larm och aviseringar? Inte bara mejl.
- **Kanaler:** i AI-appen (primärt), transaktionsmejl (out-of-band), ev. push/Slack via webhooks.
- **Preferenser per användare:** vilka notiser, vilken kanal, **stör-ej**-tider.
- Default: viktigt i appen; sammanfattningar/rapporter via mejl om man valt det. (OPEN-GAPS #9)

## Säkerhet

- **Alla åtgärdslänkar** (`setup_url`, `link_url`, `relink_url`, `verify_url`) bär en **signerad,
  kortlivad token** (HMAC/JWT, kort TTL, engångsbruk där möjligt). Aldrig lösenord eller hemligheter
  i klartext i mejlet.
- **Rate-limit** utgående (`rate_limit_per_min`) mot missbruk och för att skydda avsändarryktet.
- **Inga spårpixlar** i säkerhets-/auth-mejl.
- Logga sändning (mall, mottagare, status) för felsökning — men aldrig token-innehållet.

## Faser
1. **SMTP-provider + 3 kärnmallar** (`invite`, `account_link`, `auth_required`) — räcker för
   onboarding-flödet. Dogfooda via Purelymail-SMTP.
2. **SES-adapter** + DKIM/SPF/DMARC på `notify.`-subdomän.
3. **Resterande mallar** (security, verify, report, operator, provisioning).
4. **Mailgun/MailerSend-adaptrar** + lokalisering + billing-mallar.

## Acceptanskriterier
- [ ] `system_mail.provider` byter leverantör utan kodändring.
- [ ] Systemmejl skickas från egen `notify.`-subdomän med giltig SPF/DKIM/DMARC.
- [ ] Mallarna renderas multipart (plaintext + HTML) och brandas från `brand.yaml`.
- [ ] Alla åtgärdslänkar är signerade och kortlivade; inga hemligheter i mejlet.
- [ ] Dogfooding fungerar via SMTP/Purelymail; SES är en config-rad bort.
