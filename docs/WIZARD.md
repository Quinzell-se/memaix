# Installations-wizarden — fullständigt flöde

Den guidade uppsättningen (`memaix init`, eller `make install` när config saknas). Tar en operatör
från `git clone` till en körande, verifierad instans — utan att redigera YAML för hand. Samlar det
som annars är utspritt i INSTALL, SELF-HOST-STACK, BACKENDS, PER-USER-OAUTH och AUTO-INSTALLER.

## Principer
- **Interaktiv som standard**, men kan köras **non-interaktivt** (config/flaggor förifyllda).
- **Idempotent och återupptagbar:** en statefil spårar avklarade steg; omkörning fyller bara luckor.
- **Validera medan du går:** varje steg kontrollerar sin egen input innan nästa.
- **Transparent:** wizarden skriver vanliga config-filer du kan läsa och ändra efteråt.

## Stegen

| # | Steg | Frågar | Skriver | Validerar |
|---|---|---|---|---|
| 0 | **Förkontroll** | — | — | docker finns, portar lediga, domän pekar rätt |
| 1 | **Brand** | namn, tagline, support-mejl, färg | `config/brand.yaml` | namn ej tomt |
| 2 | **Domän & tunnel** | publik URL; tunnel: cloudflared-token \| egen proxy | `config/memaix.yaml` (server, tunnel) | URL svarar / token giltig |
| 3 | **Hemligheter** | — (auto) | `.env` (OAuth-nyckel, admin-lösen) | nycklar genererade |
| 4 | **Kalender & filer** | bundlad Nextcloud \| extern Nextcloud \| Gmail/M365 | `config/memaix.yaml` (defaults) | backend nåbar |
| 5 | **Mejlleverantör** | Purelymail \| generisk IMAP \| Gmail \| M365 | `.env` + `acl.yaml` (per projekt) | inloggning/token funkar |
| 6 | **Projekt & personer** | projekt, användare, grants (roller) | `config/acl.yaml` | minst en owner; refs stämmer |
| 7 | **Provisionering** | — (kör) | containrar, NC-konton, mejlkonton, vaults | allt startade |
| 8 | **AI-connector** | vilka AI:er ni kör | skriver ut URL + instruktioner | OAuth-metadata nåbar |
| 9 | **Doctor** | — (kör) | verifieringsrapport | alla kontroller gröna |

## Detaljer per steg

**0. Förkontroll.** docker/compose finns, portar 8080/8081 lediga, `public_url`-domänen pekar mot
servern (eller tunnel vald). Stoppar tidigt med tydligt fel.

**1. Brand.** Namn, tagline, support-mejl, primärfärg → `brand.yaml`. Default "Memaix" (white-label).

**2. Domän & tunnel.** Publik URL (= OAuth-issuer). Val: **cloudflared** (klistra in tunnel-token,
wizarden aktiverar profilen) eller **egen reverse proxy** (`tunnel.provider: none`). Påminner:
ingen Access framför, Bot Fight av (SECURITY.md).

**3. Hemligheter.** Genererar OAuth-signeringsnyckel och Nextcloud-admin-lösen → `.env`. Inget att
fylla i manuellt.

**4. Kalender & filer.** 
- **Bundlad Nextcloud** (default): aktiverar profilen, körs på samma maskin (SELF-HOST-STACK).
- **Extern Nextcloud:** ange bas-URL.
- **Gmail/M365:** hoppar Nextcloud, sätter backend-typ (BACKENDS.md); OAuth-app i steg 8.

**5. Mejlleverantör** (leverantörsoberoende):
- **Purelymail:** be om API-token → wizarden skapar användare/domäner per projekt via API:t →
  credentials till `.env`. Kundens egna konto (SELF-HOST-STACK).
- **Generisk IMAP:** host/port/användare/lösen.
- **Gmail/M365:** OAuth-vägen (steg 8 / PER-USER-OAUTH.md).

**6. Projekt & personer.** Loop: lägg projekt (namn + vilka backends från steg 4–5) och personer
(mejl→oauth_sub + grants per projekt). Kräver minst en `owner`. Skriver `acl.yaml`.

**7. Provisionering.** Kör bootstrap: starta containrar → provisionera Nextcloud (användare,
app-lösen→`.env`, kalendrar) → provisionera mejl (Purelymail-API eller instruktion) → seed-vaults
(kopiera `vault-template/`, `git init`). Idempotent.

**8. AI-connector.** Skriver ut connector-URL:en och korta instruktioner per vald AI (AI-CLIENTS.md).
För Gmail/M365: guidar OAuth-app-registreringen (intern Workspace-app / single-tenant Entra-app —
kan inte fullautomatiseras, konsol-steg) och tar emot client-id/secret → `.env`.

**9. Doctor.** Verifierar: gateway frisk, OAuth-metadata nåbar, NC-användare finns, app-lösen
giltiga, kalendrar skapade, mejl-inloggning funkar, vaults git-initierade, RBAC-isolering håller
(testanvändare utan grant nekas). Grön/röd per kontroll med pekare till felet.

## Lägen
- **Interaktivt:** `memaix init` — frågar steg för steg.
- **Non-interaktivt:** förifylld `config/*.yaml` + `.env` → `memaix init --yes` kör utan frågor
  (för repeterbara kundinstallationer hos dig som leverantör).
- **Omkörning:** `memaix init` igen läser statefilen, hoppar avklarat, reparerar resten.

## Kommandon
```
memaix init       # wizarden (detta dokument)
memaix doctor     # bara verifieringen (steg 9)
memaix update     # ny image + migrera + kör om idempotent provisionering
```

## Acceptanskriterier
- [ ] En icke-teknisk operatör tar sig från clone till körande instans utan att röra YAML.
- [ ] Wizarden stödjer Purelymail (API), generisk IMAP och Gmail/M365.
- [ ] Omkörning är idempotent och reparerar en halvfärdig installation.
- [ ] `memaix init --yes` ger repeterbar non-interaktiv kundinstallation.
- [ ] Doctor körs sist och rapporterar grönt innan wizarden säger "klart".
