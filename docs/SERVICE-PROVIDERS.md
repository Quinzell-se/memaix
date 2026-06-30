# För tjänsteleverantörer — sälja installation & hosting

Memaix är öppen källkod (AGPL-3.0). Vem som helst kan självhosta gratis. Affärsmodellen för dig
som leverantör ligger i **tjänsten**, inte i kodlåsning.

## Modell: en instans per kund, på kundens infra
- **Du säljer installation och drift** — inte tillgång till dina egna maskiner.
- Varje kund får en **egen instans** på sin egen server/molnhosting, med **eget namn, egen domän,
  egna tunnlar** (se WHITE-LABEL.md).
- Du tar betalt för: uppsättning, konfiguration, härdning, uppgraderingar, övervakning, support.

## Varför single-tenant passar modellen
- Ingen delad dataplan → enklare isolering och dataskydd (kundens data stannar hos kunden).
- Inget multi-tenant-ansvar för dig → mindre juridisk och teknisk risk.
- Kunden äger sin instans även om de slutar köpa din drift — lågt inlåsningsmotstånd vid sälj.

## Typiskt leveranspaket
1. Provisionera kundens server (deras moln/maskin).
2. Klona Memaix, sätt `brand.yaml`, `memaix.yaml`, `acl.yaml`.
3. Koppla kundens domän + tunnel, härda enligt SECURITY.md.
4. Seed-vaults + onboarding-intervju för deras team.
5. Löpande: uppgraderingar, övervakning, support — det återkommande värdet.

## Managed hosting (Tier 2) — vem äger molnkontot?
Vill kunden att *du* installerar **och** driftar (inte bara installerar), blir du sannolikt
**personuppgiftsbiträde** → DPA krävs (se LEGAL.md §2). Två sätt, single-tenant i båda:

- **A — kundens eget molnkonto, du som operatör (rekommenderas):** kunden öppnar kontot
  (Hetzner/GCP/AWS …) och ger dig driftåtkomst. Data + faktura ligger hos kunden. Lägst juridisk
  exponering, trivial exit, linjerar med suveränitetspitchen.
- **B — ditt egna, isolerat projekt per kund:** du äger infran, kunden är hyresgäst på en
  **dedikerad, isolerad** instans (eget projekt/sub-konto, aldrig delad maskin). Fullt biträde →
  hela DPA-apparaten, du bär intrångsrisken. Prisa in ansvaret.
- **Aldrig:** delad multi-tenant på din infra (GDPR-risk + bryter värdeerbjudandet).

I båda fallen: håll instansen + datan **portabel** (kunden kan flytta den) så anti-inlåsnings-löftet
består även när du hostar. Firebase/Firestore är fel runtime — det här är en VM/Compose-stack.

## Paketera install & konfiguration

**Engagemangsmodeller**
1. **Fast engångspris (produktifierad setup) — rekommenderas.** Definierat scope, kunden driftar
   själv efteråt. Tydligast för kund, tvingar fram automation.
2. **Setup + drift-retainer (managed).** Engångs + månadsavgift; kräver biträdesroll/DPA (ovan).
3. **Tid & material.** För oklart/rörligt scope eller tung specialintegration.
4. **Pilot/design-partner (rabatterat).** Första 3–10 kunderna mot referens + uppmätt supporttid.

**Scope-faktorer som driver priset**
Antal backends (mejl vs + Nextcloud + forge) · per-user OAuth × antal användare · white-label
(domän/branding/tunnel) · lokal modell/GPU (LOCAL-MODEL.md) · migrering/import (IMPORT.md) ·
antal projekt/personer i `acl.yaml` · härdnings-/compliance-nivå (reglerad bransch).

**Prisnivåer (setup, engångs — förslag att validera)**
| Nivå | Scope | Pris |
|---|---|---|
| **Bas** | 1 instans, mejl + vault, 1–3 användare, standarddomän, ingen migrering | €500–800 (~6–9 000 SEK) |
| **Standard** | + Nextcloud + forge, white-label, 3–10 användare, lätt import | €1 000–2 000 (~11–23 000 SEK) |
| **Komplex** | + lokal modell/GPU, reglerad bransch (DPA/härdning), tung migrering, många projekt | €2 500–5 000+ / offert |

**Löpande drift (om managed):** €40–90/mån per instans + infra (€15–40/mån, passthrough till kund)
+ ev. PM-modul €20–40/mån. Se BUSINESS-CASE.md §4–5.

**Räkna baklänges:** vid ~800–1 200 SEK/tim (€80/tim i BUSINESS-CASE) måste en Bas-setup (€600)
klaras på ~6–8 h för att gå ihop. Tar den 15 h manuellt → förlust. **Automation (installer/doctor/
observability) avgör om setup-priset är vinst eller förlust** (BUSINESS-CASE §5).

> Alla siffror är **förslag att validera**, inte satta priser: mät faktisk tid hos en design-partner,
> bekräfta betalningsvilja med ≥3 piloter, säkra positiv marginal *efter* supporttid (BUSINESS-CASE §10).

## AGPL i praktiken
Du får sälja drift och installation fritt. Distribuerar du en modifierad version (även som
nättjänst) ska dina ändringar vara öppna. Branding och config räknas inte som dolda
modifikationer. Vill du senare kunna stänga vissa tilläggsmoduler: håll dem som separata,
tydligt avgränsade plugins och ta juridisk rådgivning om licensgränser.
