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

## AGPL i praktiken
Du får sälja drift och installation fritt. Distribuerar du en modifierad version (även som
nättjänst) ska dina ändringar vara öppna. Branding och config räknas inte som dolda
modifikationer. Vill du senare kunna stänga vissa tilläggsmoduler: håll dem som separata,
tydligt avgränsade plugins och ta juridisk rådgivning om licensgränser.
