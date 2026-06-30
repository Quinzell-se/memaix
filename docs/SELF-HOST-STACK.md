# Self-host-stacken — topologi & mejl-provisionering

Två deploy-beslut för den rena self-host-vägen (Nextcloud + mejlleverantör). Adapter-modellen
(`BACKENDS.md`) gör att en kund lika gärna kan köra Gmail/M365 — detta gäller dem som vill maximalt
dataägande.

## 1. Körs Nextcloud på samma maskin som Memaix?

**Standard: ja, samma maskin.** `docker-compose.yml` har Nextcloud som en profil i samma stack —
gateway + Nextcloud + (valfri) cloudflared på en box. Minnesvaulten (git) ligger också där.

- **Passar:** single-tenant, små team — en blygsam VPS klarar allt.
- **Att tänka på:** Nextcloud är måttligt tung (PHP + databas). Vid större team eller hög last,
  bryt ut Nextcloud till egen maskin/managed Nextcloud.
- **Inte hårdkopplat:** config kan peka på en **extern** Nextcloud (`defaults.nextcloud_base_url`
  eller per projekt). Bundlad som default, frikopplingsbar vid behov.

Rekommendation: bundla på samma maskin för enkelhet; erbjud extern Nextcloud som uppgraderingsväg.

## 2. Mejl: återförsäljare eller wizard?

> Full mejlstrategi (posturer, leverantörsval MXroute/Mailcheap/Purelymail, transaktionsmejl,
> slutanvändar-UI): **[MAIL.md](MAIL.md)**. Sammanfattning nedan.

### Slutsats: wizard via API — inte master-konto-reselling
- **Purelymail saknar kundunika paneler** → fungerar för eget konto (Posture A), inte som skalbar
  reseller-affär. Det har dock ett **API** för provisionering (skapa/ändra/radera användare, domäner).
- **v2-beslut:** mejl-reseller är **struken** (BYO-infra). Behåll *projektspecifik provisionering* i
  kundens egna leverantör för tillfälliga konsulter. (MXroute/Mailcheap kvarstår bara som bakgrund i
  MAIL.md.) Se REVIEW-RESPONSE.md.

### Rekommenderad modell: wizard provisionerar kundens *egna* Purelymail-konto
Wizarden tar kundens egna Purelymail-API-token och skapar deras brevlådor/domäner via API:t.
- ✅ Kunden äger konto **och** billing — vi automatiserar bara uppsättningen.
- ✅ Passar single-tenant + "kunden äger sin data".
- ✅ Ingen återförsäljar-deal krävs.

### Undvik: ett master-konto som "återförsäljning"
Att lägga alla kunders användare under *ett* eget Purelymail-konto:
- ⚠️ ToS-osäkert (verifiera med Purelymail innan något sådant).
- ⚠️ Bryter dataisoleringen — alla kunder i samma konto.
- ⚠️ Krockar med single-tenant-principen och "kunden äger sin data".

### Gör det leverantörsoberoende
Bygg wizarden som ett **"mejlleverantör-steg"**, inte ett Purelymail-steg:
- **Purelymail** = automatiserat alternativ (API-provisionering).
- **Valfri IMAP/SMTP** = manuellt alternativ (kunden anger host/användare/lösenord).
- **Gmail/M365** = OAuth-vägen (se `BACKENDS.md`).

Purelymail är en liten indie-leverantör → **lås inte produkten till dem** (beroenderisk). Gör dem
till ett bekvämt default, inte ett krav.

## Provisioneringssteg (wizard, mejl)
1. Fråga: vilken mejlleverantör? (Purelymail / annan IMAP / Gmail / M365)
2. Purelymail: be om API-token → skapa användare/domäner per projekt via API → skriv in
   credentials i `.env` (refereras från `acl.yaml`).
3. Bobn IMAP: be om host/port/användare/lösenord.
4. Gmail/M365: starta OAuth-app-registrering (se `PER-USER-OAUTH.md`).

## Acceptanskriterier
- [ ] Standardinstall kör Nextcloud + Memaix på samma maskin; config kan peka på extern Nextcloud.
- [ ] Mejl-wizarden provisionerar kundens egna Purelymail-konto via API utan manuell webbsetup.
- [ ] Wizarden stödjer även generisk IMAP och Gmail/M365 — Purelymail är default, inte krav.
- [ ] Inga kunddata blandas under ett gemensamt mejlkonto.
