# Setup-gränssnittet — webb-wizard vs native app

Beslut om hur den interaktiva uppsättningen (brand, backends, mejlleverantörs-API, OAuth-länkning,
bekräftelser) presenteras för operatören. Kompletterar `WIZARD.md` (flödet) med *bäraren*.

## Beslut
**En liten lokal webb-wizard som paketet själv serverar — inte en native Win/Mac-app.** Plus
CLI/declarative config för repeterbara installationer. Ingen native desktop-app i v1.

## Varför webb, inte native
- **Memaix körs på en server, ofta headless** (VPS via SSH). En Win/Mac-app passar inte en
  headless Linux-box — bara desktop-install.
- **OAuth-kopplingar kräver en webbläsare ändå** (Gmail/M365/Cloudflare redirects). Webben är deras
  naturliga hem; CLI måste ändå poppa en browser eller köra device-code.
- **Industristandard** för självhostade serverprodukter: Nextcloud, Home Assistant, Proxmox,
  GitLab, Syncthing, Pi-hole — lokal web-setup, ingen native installer.
- **Lågt underhåll** vs native (kodsignering, notarisering, auto-update, två OS-mål).

## Jämförelse
| | Webb-wizard | Native Win/Mac | Ren CLI |
|---|---|---|---|
| Headless server | ✅ | ❌ | ✅ |
| OAuth-redirects | ✅ | ⚠️ | ❌ |
| Icke-tekniker | ✅ | ✅ | ❌ |
| Repeterbart (leverantör) | ⚠️ | ❌ | ✅ |
| Underhåll | Lågt | Högt | Lågt |
| Attackyta | Måste härdas | Medel | Låg |

## Roller
- **Webben gör det interaktiva:** brand, domän/tunnel, backends, mejlleverantörs-API-token
  (Purelymail/IMAP/Gmail/M365), OAuth-länkning (Gmail/M365), projekt/personer, kör provisionering, doctor.
- **CLI/config gör det repeterbara:** `memaix init --yes` med förifylld YAML för dig som
  installerar åt många kunder. Samma motor bakom båda.
- **Native desktop:** ej nu. Vid behov senare → tunn Tauri-wrapper runt samma webb (billigt).

## Säkerhetsdesign (obligatorisk — setup-ytan är högprivilegierad)
Setup-webben skriver config, tar emot hemligheter (mejlleverantörs-API, OAuth) och provisionerar konton.
Den måste därför:

1. **Localhost-bind.** Aldrig publikt. Nås via SSH-tunnel (`ssh -L`) eller den autentiserade
   Cloudflare-tunneln. Setup-porten exponeras aldrig öppet.
2. **Engångs-setup-token.** Skrivs ut i terminalen, måste matas in i webben (jfr Jupyter/Nextcloud/
   GitLab). Stoppar drive-by-åtkomst.
3. **Självavstängande.** Setup-läget och dess config-skrivande endpoints stängs av när installationen
   är klar — ingen stående yta i drift.
4. **Hemligheter åt ett håll.** Tas emot, lagras serverside (krypterat), ekas aldrig tillbaka till
   webbläsaren, loggas aldrig.
5. **CSRF + PKCE + state** i alla formulär och OAuth-flöden.
6. **Minimal frontend.** Server-renderad, få/inga JS-beroenden — undvik tung SPA (attackyta +
   supply chain).
7. **TLS.** Via tunneln eller lokalt cert; aldrig hemligheter i klartext.

## Arkitektur
- Ett **setup-läge** i samma paket: `memaix init` startar en liten webbserver på
  `127.0.0.1:8088`, skriver ut URL + engångstoken.
- Operatören öppnar den (lokalt eller via SSH-/Cloudflare-tunnel), går igenom `WIZARD.md`-stegen.
- Vid "klart" kör den doctor, skriver config, och **stänger setup-läget**. Runtime-gatewayen har
  inga config-skrivande endpoints.

## Acceptanskriterier
- [ ] Setup-webben är åtkomlig bara via localhost/tunnel, aldrig öppet publikt.
- [ ] Engångstoken krävs för att nå wizarden.
- [ ] Setup-endpoints är avstängda efter slutförd installation.
- [ ] Hemligheter ekas aldrig tillbaka till klienten och loggas aldrig.
- [ ] `memaix init --yes` (CLI) ger samma resultat utan webben, för repeterbara installationer.
