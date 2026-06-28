# Juridik & ansvar — checklista (ej juridisk rådgivning)

> **Brasklapp:** Detta är ingen juridisk rådgivning. Det är ett riskregister och en checklista att
> lämna till en kvalificerad **dataskyddsjurist (GDPR/EU)** innan kommersiell lansering. Memaix låter
> en AI agera på personuppgifter (mejl, kalender, kontakter) → juridiken måste granskas av proffs.

## 1. Ansvar när AI:n agerar
- Memaix är **mjukvara/middleware** — användaren ansvarar för att granska AI:ns utdata.
- **ToS/EULA** ska placera ansvaret rätt: leverans "i befintligt skick", ansvarsbegränsning, krav på
  mänsklig granskning. Disclaimer: AI-utdata kan vara fel, granska före användning.
- **Designen sänker redan ansvaret** (se §8): utkast-bara mejl + mänsklig bekräftelse för destruktiva
  åtgärder gör att Memaix aldrig autonomt skickar/raderar. Det är en *juridisk* riskdämpare, inte bara UX.

## 2. GDPR-roller (avgörande, och beror på modellen)
- **Självhostat:** kunden kör mjukvaran själv → kunden är **personuppgiftsansvarig (controller)**.
  Memaix-projektet levererar bara kod.
- **Managed (du installerar/driftar åt kund):** du blir sannolikt **personuppgiftsbiträde (processor)**
  → kräver ett **personuppgiftsbiträdesavtal (DPA)** med varje kund.

## 3. AI-leverantören är ett underbiträde — och datan lämnar landet
- När AI:n läser ett mejl via gatewayen går innehållet till **AI-leverantörens servrar** (Anthropic/
  OpenAI/Mistral). Det är en **överföring till tredje part**, ofta till **USA** (Schrems II /
  EU-US Data Privacy Framework).
- Kunden måste **veta och godkänna** att deras data går till vald AI. Underbiträdeskedjan ska
  dokumenteras (AI-leverantör, hosting, mejlleverantör).
- **AI-planen spelar juridisk roll:** enterprise-/team-planer (Claude/OpenAI/Mistral) erbjuder ofta
  **ingen träning på data + DPA**; konsumentplaner kanske inte. För känslig data → kräv rätt plan.

## 4. EU AI Act
- Memaix som produktivitetsassistent är troligen **låg/minimal risk**, men **transparenskrav** kan
  gälla (användaren ska veta att den interagerar med AI). Bedöm riskklass; undvik high-risk-användning
  (t.ex. automatiserade beslut om individer) utan särskild granskning.

## 5. Sekretess i reglerade branscher
- Advokat/vård/finans: att skicka klient-/patientdata till en tredjeparts-AI kan bryta
  **tystnadsplikt/sekretess** om inte AI-leverantörens villkor (ingen träning, dataresidens) håller.
- Self-host hjälper för *lagring*, men i samma sekund datan går till AI:n gäller **AI-leverantörens**
  villkor. Dokumentera detta tydligt mot sådana kunder.

## 6. Mejl-specifikt
- Memaix skickar transaktions-/personlig mejl, inte marknadsföring → CAN-SPAM/ePrivacy-massutskick
  gäller inte normalt. Men **kunden är avsändaren** och ansvarig för innehållet.
- Åtkomst sker till **användarens egen** brevlåda med dennes samtycke (OAuth/kontolänkning).

## 7. Dokument som behövs (innan kommersiell lansering)
- **ToS/EULA** (tjänst + mjukvara), **Privacy Policy**, **DPA** (för managed), **AUP** (acceptabel
  användning — ingen olaglig användning/spam), **underbiträdeslista**, **SLA** (om hosting säljs).
- **AGPL-efterlevnad:** tillgängliggör källkod (även white-labelat); redan känt (LICENSE/WHITE-LABEL).

## 8. Hur designen redan dämpar juridisk risk
| Designval | Juridisk nytta |
|---|---|
| Self-host, single-tenant | Kunden behåller kontroll → controller-roll, dataresidens |
| Utkast-bara mejl + bekräftelse för destruktiva åtgärder | Memaix agerar aldrig autonomt → lägre ansvar |
| Audit-logg | Spårbarhet för compliance (vem gjorde vad) |
| Data retention + purge | Rätt att glömmas, dataminimering |
| BYOK (enterprise) | Kunden äger nycklarna → starkare dataägande |
| "Dumpa aldrig" / retrieval | Dataminimering mot AI-leverantören |

## 9. Att ta till jurist (åtgärdslista)
- [ ] Granska controller/processor-modellen för både self-host och managed.
- [ ] Ta fram DPA + underbiträdeslista (inkl. AI-leverantörer + tredjelandsöverföring).
- [ ] Bekräfta vilka AI-planer som krävs för känslig data (no-training + DPA).
- [ ] Bedöm EU AI Act-riskklass + transparenskrav.
- [ ] ToS/EULA med ansvarsbegränsning + krav på mänsklig granskning.
- [ ] Vägledning för reglerade branscher (sekretess vs AI-leverantörens villkor).

## Acceptanskriterier (för "juridiskt lanseringsklar")
- [ ] En jurist har granskat roller, DPA och tredjelandsöverföring.
- [ ] Kunden informeras tydligt om vart data går (vilken AI) innan inkoppling.
- [ ] ToS/Privacy/DPA/AUP finns och är länkade i produkten.
- [ ] Designens riskdämpare (utkast-bara, bekräftelse, audit, purge) är aktiva som standard.
