# Mejlstrategi — leverantörer, reseller-postur & transaktionsmejl

Adapter-modellen (`BACKENDS.md`) är leverantörsoberoende — vilken IMAP/SMTP som helst funkar. Detta
dokument handlar om *affärsvalet* bakom: vill Memaix bara koppla till kundens mejl, eller även
**sälja** mejl?

## Två posturer

**A. Bring/own your mail** (single-tenant-renhet). Kunden har eget konto (Purelymail, Gmail, M365,
valfri IMAP). Memaix kopplar via adapter. Ingen återförsäljning, minst ansvar.

**B. Memaix säljer förvaltad mejl** (du är återförsäljare). Du provisionerar brevlådor och fakturerar.
Kräver en **white-label reseller-backend** med kundpaneler.

De utesluter inte varandra — adaptern stödjer båda. Frågan är om du *lägger till* förvaltad mejl som
intäktsström.

## Leverantörsjämförelse

| Leverantör | Modell | Reseller-panel | API-provisionering | Bäst för |
|---|---|---|---|---|
| **Purelymail** | Lagring/usage | ❌ ingen kundpanel | ✅ enkelt API | Posture A (eget konto), egna projekt |
| **MXroute** | Lagringspott, reseller | ✅ DirectAdmin, white-label, billing-isolering | ⚠️ via DirectAdmin (går, men tyngre) | **Posture B** — sälja mejl med kundpaneler |
| **Mailcheap** | Dedikerad server, API-first | ⚠️ (mindre panel) | ✅✅ kraftfullt API | **Posture B djupintegrerat** — auto-skapa brevlåda vid signup |
| **Gmail / M365** | Per användare (deras) | n/a (kundens egen) | OAuth | Kund som redan har dem |

> Priser rör sig — verifiera aktuellt (MXroute Reseller 75 ≈ $30/kvartal/75 GB, Reseller 200 $25/mån;
> Mailcheap från ~$5–10/mån). Purelymail saknar kundunika paneler → fungerar för polare, inte som
> skalbar reseller-affär.

## Rekommendation

- **Behåll adaptern leverantörsoberoende** — lås inte produkten till en leverantör.
- **Posture A (default):** kundens egna konto. Purelymail/Gmail/M365. Det vi redan specat.
- **Posture B när du vill sälja mejl:**
  - **MXroute** som pragmatisk start — riktig white-label-panel där kunder själva byter lösenord,
    skapar alias och hanterar sin inkorg. Deliverability och IP-rykte sköts av MXroute.
  - **Mailcheap** när du vill att *Memaix själv* skapar en brevlåda automatiskt vid registrering
    (API-first) — djupare plattformsintegration.
- Börja inte med Posture B dag ett: förvaltad mejl = supportbörda, deliverability-ansvar och
  abuse-hantering. Lägg till den när efterfrågan finns.

## Kritiskt: separera transaktions-/systemmejl

Memaix skickar **själv** systemmejl — automatiska, händelsestyrda, ett-till-en. Inte
marknadsföring, inte massutskick.

### Vad transaktionsmejlen används till
**Till slutanvändare:**
- **Inbjudningar** — "du har fått access till projekt X, här är din uppkopplingslänk".
- **Onboarding / kontolänkning** — `/link/google`-länk, setup-token, "koppla din Gmail/M365".
- **`auth_required` / omlänkning** — token har gått ut, länka om ditt konto.
- **Säkerhetsnotiser** — ny connector/enhet kopplad, konto avlänkat, behörighet ändrad.
- **Verifiering** — bekräfta en mejladress vid registrering.
- **Schemalagda rapporter (valfritt)** — morgonbrief, dagsavslut, `pm_status_report` till ledning,
  *om* mottagaren vill ha dem mejlade istället för i assistenten.

**Till operatör/leverantör (du):**
- **Drift-/systemlarm** — doctor-fel, backup-status, certifikat som löper ut, kvot-varningar.
- **Provisioneringsresultat** — kundinstallation klar/misslyckad.

**Vid försäljning av hosting:**
- **Billing** — fakturor, förnyelsepåminnelser, trial som löper ut.

> **Princip:** föredra notis **i assistenten** där det går (det är primärt UI). Transaktionsmejl är
> den **out-of-band-kanal** som behövs när assistenten inte är rätt/tillgänglig yta — innan en person
> är uppkopplad (inbjudan/onboarding), säkerhetslarm, operatörslarm, mejlade rapporter och billing.

### Varför separat leverantör
Det får **inte** gå via brevlådeleverantören:
- Purelymail/MXroute **tillåter inte** massutskick/automatiserade blast → bryter ToS, sänker
  IP-ryktet och kan stänga kontot.
- Routa Memaix egen utgående systemmejl via en **transaktionsleverantör**: Amazon SES, Mailgun
  eller MailerSend.

**Ren separation:** brevlådeleverantör = människors inkorgar; transaktionsleverantör = systemmejl.
Config: `system_mail: { provider: ses|mailgun|mailersend, ... }` skilt från projektens `mail`-backend.

## Slutanvändarens gränssnitt — du behöver inte välja

En riktig brevlåda (MXroute m.fl.) stödjer **allt** samtidigt, eftersom det är standard-IMAP:

1. **Assistenten som primärt gränssnitt** — AI:n läser/skriver mejl via adaptern. Memaix kärnvärde;
   kräver inget webmail alls.
2. **Native klient** (telefon/Outlook) — kunden lägger in IMAP/SMTP-uppgifterna. Funkar alltid.
3. **Nextcloud Mail** (valfritt) — webmail i samma Nextcloud-UI som filer/kalender. Snygg enad
   upplevelse, men en extra del att drifta.

**Rekommendation:** led med *assistenten + native klient* (lägst friktion). Erbjud Nextcloud Mail
som valfri enad webmail-upplevelse för dem som vill ha allt på ett ställe. Tvinga inte fram ett val
— samma brevlåda räcker för alla tre.

## iOS native Mail & push — inte ett leverantörsval

iOS inbyggda Mail-app får **ingen push** från små/självhostade leverantörer. Apple slopade IMAP
IDLE och gömde push bakom en proprietär mekanism (`XAPPLEPUSHSERVICE`) som kräver certifikat *från
Apple*. Bara enstaka leverantörer (Fastmail) har dem.

- **Purelymail:** kan inte → poll/manuell hämtning på iOS Mail (dokumenterar det själva).
- **MXroute:** stödjer IDLE men **ingen** push-mekanism → **samma begränsning**. Att byta hit löser
  alltså *inte* iOS-native-Mail-problemet.

**Vad som faktiskt fixar det:**
1. Använd en **annan iOS-mejlapp** (Outlook/Spark m.fl.) — egen IDLE-koppling ger direkt notis.
2. **Fastmail** om native Mail-push är ett måste (dyrare, ingen reseller).
3. Självhostad Dovecot med Apple-push-plugin + eget APNs-cert (krångligt).

**För Memaix:** lågt problem. iOS native Mail är **inte** det primära gränssnittet — assistenten är.
Notiser går via AI-appen och transaktionsleverantören. Memaix kringgår push-gapet genom att inte
bero på iOS Mail. (Vill en kund ändå ha native-Mail-push: rekommendera annan app, eller Fastmail.)

## Beslut som behövs
- [ ] Ska Memaix erbjuda **förvaltad mejl** (Posture B) eller bara koppla kundens egen (Posture A)?
- [ ] Om B: **MXroute** (panel-först) eller **Mailcheap** (API-först) som start?
- [ ] Vilken transaktionsleverantör för systemmejl (SES/Mailgun/MailerSend)?
- [ ] Vilket slutanvändar-UI promotas — assistent+native, eller även Nextcloud Mail?
