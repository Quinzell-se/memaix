# Enterprise-tiern

Vad ett storföretag behöver utöver kärnan, och hur det läggs på **utan** att bryta single-tenant.
Bakgrund: `PRODUCT.md` ("Har den lika stor nytta i ett stort företag?"). Enterprise = den betalda
tiern + tjänster.

## När den behövs (signaler)
Central identitet (anställda kommer och går), efterlevnadskrav (audit, dataresidens, DPA), många
team/projekt, och krav på SLA/support. Solo→SMB klarar sig på kärnan; det här är för dem som inte gör det.

## 1. Identitet — SSO + SCIM (den stora)
Kärnan mappar `oauth_sub → användare` manuellt i `acl.yaml`. Det skalar inte i ett storföretag.

- **SSO (SAML/OIDC)** mot kundens IdP (Entra ID, Okta, Google Workspace) — anställda loggar in mot
  företagets identitet, inte en Memaix-lokal.
- **SCIM-provisionering** — användare/grupper synkas automatiskt från IdP:n. Slutar någon →
  **avetableras automatiskt** (kritiskt för säkerhet — ingen kvarglömd access).
- **Gruppbaserad RBAC** — mappa IdP-grupper → projekt-grants/roller, istället för per-användare i
  `acl.yaml`. `acl.yaml` definierar då projekt/resurser + grupp→grant; individerna kommer från IdP:n.

## 2. Audit & efterlevnad
- **Immutabel audit-logg** — varje verktygsanrop, access och config-ändring; exporterbar till SIEM
  (syslog/JSON). Bygger på `features.audit_log` men gör den tamper-evident och exporterbar.
- **Retention-policy** + access-reviews/certifiering.
- **Efterlevnadsläge:** dataresidens (self-host hjälper redan), GDPR/SOC2-underlag, DPA, DPIA-stöd.

## 3. Styrning & policy
- **Org-admin-roll** skild från projekt-owner.
- **Policyer:** vilka backends tillåts, `allow_send` på org-nivå, dataretention, vilka AI-klienter
  som får kopplas in.
- **Godkännandeflöden** för känsliga åtgärder.

## 4. Säkerhetshärdning
- **BYOK / KMS** — kundens egen nyckel för secrets- och token-kryptering (HashiCorp Vault / molnets KMS
  istället för `.env`).
- **Nätverk:** IP-allowlisting, mTLS-option.
- **MFA** påtvingad via IdP:n.

## 5. Flotthantering (många instanser)
- **Central konsol** för att hantera flera instanser/projekt: policymallar, aggregerade doctor-resultat,
  orkestrerad uppdatering över flottan. Gäller även **dig som leverantör** med många kundinstanser.
- **Kritiskt designkrav:** management-planet hanterar **config, policy och hälsa — aldrig kunddata**.
  Datan stannar i varje single-tenant-instans. Bobrs bryts isoleringen som är hela poängen.

## 6. Support & SLA (kommersiellt)
SLA-nivåer, dedikerad support, onboarding-tjänster. Inte teknik — paketering.

## Hur det passar arkitekturen
- **Single-tenant bevaras** — en instans per kund/org, data isolerad. Det är en *fördel* för
  enterprise (dataresidens), inte ett hinder.
- **IdP ersätter statiska användare** — SSO för authN, SCIM + grupper för authZ. Projekt/resurser
  förblir i config; individer kommer utifrån.
- **Audit/BYOK/policy** är pålägg på befintliga subsystem, inte en omskrivning.
- **Management-planet rör aldrig kunddata** — bara styrning och hälsa.

## Open-core & licensiering
Kärnan är AGPL och fri. Enterprise-modulerna (SSO/SCIM, audit-export, flottkonsol, BYOK) är den
**betalda tiern** — dual-licensierade av dig som upphovsrättshavare, eller som separata kommersiella
moduler. Vanlig open-core-modell. Undvik att låsa *grundläggande* säkerhet bakom betalvägg (dålig
goodwill); lås det som faktiskt bara storföretag behöver (SCIM, SIEM-export, flotthantering).

## Faser
1. **SSO (OIDC)** mot en IdP + gruppbaserad RBAC.
2. **SCIM** auto-provisionering/-avetablering.
3. **Audit-export** (immutabel logg → SIEM) + retention.
4. **BYOK/KMS** + policymotor (org-admin).
5. **Flottkonsol** (config/policy/hälsa över instanser).

## Acceptanskriterier
- [ ] Anställd loggar in via företagets IdP (SSO); ingen lokal användare i `acl.yaml`.
- [ ] Avslutad anställd förlorar access automatiskt via SCIM.
- [ ] IdP-grupper styr projekt-roller (gruppbaserad RBAC).
- [ ] Audit-loggen är immutabel och exporterbar till SIEM.
- [ ] Secrets/token kan krypteras med kundägd KMS-nyckel (BYOK).
- [ ] Flottkonsolen hanterar policy/hälsa men når aldrig kunddata.
