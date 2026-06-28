# Memaix — produkt, marknad & pitch

## Vision (kanonisk)

> **Memaix är en AI-agnostisk ingång till ett team-gemensamt minne — projektkunskap, personkunskap
> och utvecklingsbehov — som vilken AI som helst (Claude, ChatGPT, Mistral) når. Ovanpå minnet en
> projektledaragent som håller koll på vad som ska göras, vem som gör vad, när, vilka beroenden som
> finns, och vilka konsekvenser det blir om något inte görs i tid.**
>
> **Hjärnan minns. Agenten agerar.**

## Pitch (kort)

> **Memaix — Bring your own AI. Own your memory.**
>
> AI-assistenter glömmer allt mellan sessioner, låser in dig hos en leverantör, och skickar din
> data till någon annans moln. Memaix vänder på det: en självhostad gateway som ger vilken AI som
> helst — Claude, ChatGPT, Mistral — ett **delat, beständigt minne** och tillgång till ditt mejl,
> din kalender och dina filer, bakom **en connector** med **åtkomst per projekt**. Byt AI när du
> vill; minnet och arbetssättet stannar. Datan stannar hos dig.

## Problem produkten löser

1. **AI-minnesförlust.** Varje session börjar från noll. Memaix ger ett delat, git-versionerat
   minne som varje AI läser vid start och skriver till.
2. **Leverantörsinlåsning.** Byter du från Claude till något annat tappar du hela din uppsättning.
   Memaix är AI-agnostiskt — arbetssättet bor i din vault, inte i en plattform.
3. **Data lämnar din kontroll.** Self-hosted, öppna standarder. Inget går till tredje part.
   Avgörande för integritetskänsliga branscher.
4. **Inget team-lager.** Vanliga AI-assistenter är enanvändare. Memaix ger flera personer, delad
   kontext och åtkomststyrning per projekt — externa låses till exakt ett projekt.
5. **Copy-paste-skatten.** Slut på att klistra in kontext manuellt. AI:n når källorna direkt.
6. **Splittrad kunskap.** Idéer, feedback och beslut sprids över chattar och huvuden. Memaix
   samlar dem i en gemensam, versionerad kunskapsbas + backlog.
7. **Onboarding-friktion.** Varje ny person/AI börjar från noll. Memaix intervjuar nya personer
   och bygger deras profil automatiskt.

## Funktioner → nytta

| Funktion | Nytta för användaren |
|---|---|
| En connector, alla AI:er (MCP) | Använd din favorit-AI; ingen inlåsning |
| Git-versionerat markdown-minne | AI:n minns; full historik och rollback |
| Åtkomst per projekt (RBAC) | Släpp in folk på *ett* projekt, inget annat |
| Mejl / kalender / filer via öppna standarder | Assistenten agerar på riktig data, du äger den |
| Gemensam backlog (utvärdera → besluta) | Fånga idéer/feedback strukturerat, besluta medvetet |
| Operating manual + playbooks i vaulten | Samma arbetssätt oavsett AI, för hela teamet |
| Onboarding genom intervju | Nya personer/AI:er blir produktiva direkt |
| Self-hosted, white-label | Egen data, eget varumärke, egen domän |
| Automatisk installation | Från noll till körande på minuter |

## Use cases (konkret)

- Läs och sammanfatta inkorgen på morgonen, utkast-svara på rutinmejl.
- Boka möten och hitta lediga tider över veckan.
- Fånga kundfeedback som poängsatta backlog-items, besluta vad som byggs.
- Producera utkast — offerter, rapporter, underlag — sparade som filer i rätt projekt.
- Ge en frilansare assistent-access till *ett* kundprojekt, inget annat.
- Behåll institutionell kunskap när folk kommer och går (allt i minnet).

## Fem branschscenarier

**1. Liten advokatbyrå.** Ärenden = projekt. Klientsekretess via RBAC (en jurist ser bara sina
ärenden). Assistenten drar ärendeminne, utkast-skriver korrespondens, sammanfattar handlingar.
Datan stannar on-prem → uppfyller sekretess- och dataskyddskrav. *Smärta löst: compliance + manuellt
dokumentarbete.*

**2. Byggentreprenör.** Projekt = byggarbetsplatser. Underentreprenörer (externa) låses till en
plats. Ändrings-PM och RFI:er fångas som backlog med risk-poäng. Ritningar/dokument i WebDAV,
tidplan i kalender. *Smärta löst: spridd platsinfo + externa med för bred access.*

**3. Privat vårdklinik.** Patientadministration (ej klinisk AI): bokning, kallelser, påminnelser.
Self-host ger dataresidens och GDPR-kontroll. Personal-onboarding via profilintervju, access per
avdelning. *Smärta löst: dataskydd + administrativ börda.*

**4. Kreativ-/marknadsbyrå.** Kunder = projekt. Varumärkesröst i minnet → konsekvent ton.
Frilansare per kund (externa, ett projekt). Innehållsproduktion + bildredigering (t.ex. via
Mistral). Kampanj-backlog. *Smärta löst: röstkonsekvens + frilans-access + produktionstempo.*

**5. Tillverkande SMF.** Projekt: FoU, produktion, försäljning. En ingenjör lägger en
databas-/processändring i backloggen (kategori backend) som utvärderas för nytta/komplexitet/risk
före bygge. Leverantör (extern) scopad till ett projekt. Kunskap stannar när personal byts ut.
*Smärta löst: kontrollerad ändringshantering + kunskapsbevarande.*

## Är den mest till för digitala nomader?

Nej — men det är där den *snabbaste* nyttan finns. Memaix föddes ur en-persons-företaget och
"på språng"-behovet, och solopreneuren/nomaden får full effekt direkt, med minimal overhead.

Men kärnvärdena — *äg ditt minne, ta med din AI, åtkomst per projekt, self-host* — skalar uppåt:
- **Solo / nomad / litet team:** högst omedelbar passform. Låg tröskel, stor hävstång.
- **Mellanstort:** starkt. Delad backlog, onboarding, flera projekt och externa.
- **Stort företag:** se nedan.

## Har den lika stor nytta i ett stort företag?

Värdet är **potentiellt ännu större** — integritet, dataresidens och åtkomststyrning väger tyngst
just där. Men ett storföretag kräver mer innan det passar fullt ut:

- **Identitet:** SSO (SAML/OIDC), SCIM-provisionering — koppla mot deras IdP istället för `acl.yaml`.
- **Efterlevnad:** audit-export, loggretention, dataklassning, granskningar.
- **Skala & drift:** flotthantering av många instanser, SLA, support.

Single-tenant-modellen är faktiskt en *fördel* för storföretag (dataisolering), men det behövs ett
**enterprise-lager** (SSO, audit, support). Slutsats: bredast omedelbar passform är solo→SMB, med en
tydlig väg uppåt via en enterprise-tier. Inte bara för nomader — men nomaden får värde *idag*,
storföretaget får värde *med enterprise-funktioner*.

## Genomgång (day-in-the-life)

Morgon, mobilen: "Vad behöver jag veta idag?" AI:n läser inkorg + kalender, ger en prioriterad
brief, flaggar tre mejl som kräver dig och utkast-svarar resten. Du dikterar en kundidé under en
promenad → den hamnar som poängsatt backlog-item. På kontoret tar du upp Claude på desktop: samma
minne, samma backlog. En frilansare loggar in mot samma connector och ser bara sitt kundprojekt.
Vid dagens slut skriver AI:n en avslutsnotering i projektets minne — morgondagens utgångsläge.
Allt på din server. Du bytte aldrig verktyg; du briefade ett system och granskade resultatet.

## Affärsmodell (sammanfattning)
Open-core, AGPL-3.0. Gratis självhostat. Intäkt via **installation + drift på kundens infra**
(white-label), och en framtida **enterprise-tier** (SSO, audit, support) och **betalda
tilläggsmoduler** (se ADDON-*.md).
