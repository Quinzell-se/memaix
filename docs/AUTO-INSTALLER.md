# Hela planen — det automatiskt installerande systemet

Mål: från `git clone` till en fungerande, säkrad, multi-AI-assistent på minuter — **repeterbart**,
för vem som helst (självhostare eller du som installerar åt en kund). Allt transparent, inget
svart-låda, idempotent (kör om utan att förstöra).

## Faser

| Fas | Vad | Status |
|---|---|---|
| **A. Bootstrap** | Hemligheter, containrar, Nextcloud-provisionering från `acl.yaml`, vault-seed | ✅ Klar (`scripts/bootstrap.py`) |
| **B. Doctor / verify** | Efter-install-koll: NC-användare finns, app-lösenord giltiga, kalendrar skapade, vaults git-init, gateway frisk, OAuth-metadata nåbar | 🔜 Nästa |
| **C. Wizard** | `memaix init` — guidad CLI som ställer frågor (brand, domän, projekt, personer, backends) och skriver config-filerna. Ingen YAML för hand. Fullt flöde: [WIZARD.md](WIZARD.md) | Planerad |
| **D. Tunnel-automation** | Valfri Cloudflare-API-integration (operatör ger API-token) → skapar tunnel + DNS automatiskt. Bobrs instruktioner | Planerad |
| **E. Livscykel** | `make update` (ny image, migrera config, kör om idempotent provisionering), backup/restore (vaults→git-remote, NC-data), avinstallation | Planerad |
| **F. Backend-adaptrar** | Utöver Nextcloud: rena IMAP/CalDAV/WebDAV + adaptrar för Google Workspace / M365 där kunden redan har dem (se [BACKENDS.md](BACKENDS.md)). Installern upptäcker och konfigurerar | Planerad |
| **G. Idempotens & state** | Statefil spårar vad som gjorts → säker omkörning, partiell reparation | Planerad |

## Designprinciper
- **Idempotent.** Kör om när som helst; redan gjort hoppas över, trasigt repareras.
- **Transparent.** All automation är läsbar kod (`scripts/`), aldrig en svart låda.
- **Single-tenant.** En instans per kund — enkel isolering, kundens data hos kunden.
- **Hemligheter aldrig i repot.** Genereras till `.env`, refereras via `*_ref`.
- **Minst privilegium.** Externa = ett projekt. Verifieras efter varje körning.
- **Validera efteråt.** `doctor` bekräftar att installationen faktiskt blev rätt.

## Komponenter
```
scripts/
  bootstrap.py     # orkestrering (Fas A)            [klar]
  doctor.py        # verifiering (Fas B)             [nästa]
  wizard.py        # config-generator (Fas C)        [planerad]
  adapters/        # backend-adaptrar (Fas F)        [planerad]
Makefile           # operatörens framsida (install / doctor / update / up / down)
.github/workflows/ # bygg + publicera gateway-image
```

## Operatörspersonas
- **Självhostaren** — kör `make install` på egen maskin/moln.
- **Tjänsteleverantören (du)** — installerar åt kund på kundens infra, white-label.
- **Framtida managed-erbjudande** — samma installer driver din egen provisionering i skala.

## Acceptanskriterier (för "färdig installer")
- [ ] `make install` ger en fungerande instans från noll utan manuell YAML (via wizard).
- [ ] `make doctor` rapporterar grönt/rött per kontroll och pekar på felet.
- [ ] Omkörning av install är säker (idempotent) och reparerar partiella installationer.
- [ ] `make update` uppgraderar utan dataförlust; vaults och NC-data backas upp.
- [ ] En kundinstallation kan göras white-label (eget namn, domän, tunnel) utan kodändring.
- [ ] Provisioneringen verifierad mot mål-Nextcloud-versionen.
