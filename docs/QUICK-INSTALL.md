# Auto-install — ett kommando i Linux-terminalen

Snabbaste vägen från färsk Linux-maskin till körande Memaix: en rad i terminalen.

## One-liner
```bash
curl -fsSL https://get.memaix.example/install.sh | sh
```
Eller — **rekommenderat för säkerhetsmedvetna** — ladda ner, läs, kör:
```bash
curl -fsSL https://get.memaix.example/install.sh -o install.sh
less install.sh        # inspektera
sh install.sh
```

## Vad skriptet gör (`install.sh`)
1. **Förkontroll:** Docker + Compose v2 — enda förkunskapen (allt annat är containeriserat). Saknas
   det → stoppar med tydlig instruktion (installerar **inte** Docker åt dig som standard — det är
   invasivt och kräver root).
2. **Hämtar koden** (`git clone --depth 1`).
3. **Kör wizarden** (`make init`) — genererar all config + hemligheter, inga filer att redigera.
4. **Reser stacken** (`make up`) och **verifierar** (`make doctor`).
5. **Skriver ut** exakt hur du kopplar in din AI.

## Oövervakad (leverantör / headless / CI)
För dig som installerar åt kund, eller scriptat:
```bash
curl -fsSL https://get.memaix.example/install.sh | MEMAIX_PROFILE=trial sh -s -- --yes
```
Styrs av miljövariabler: `MEMAIX_PROFILE` (trial|solo|team), `MEMAIX_DOMAIN`, `MEMAIX_REPO`, `MEMAIX_DIR`.

## Säkerhet — ärligt om `curl | sh`
- Att pipa fjärrkod till skalet är bekvämt men du kör kod du inte läst. **Rekommendation:** ladda ner
  och inspektera först (ovan). Skriptet är **öppen källkod** på samma GitHub och gör inget dolt.
- Skriptet ska **serveras över HTTPS**; pinna gärna en **version/checksum** och signera releasen.
- Det **auto-installerar inte Docker** (skulle kräva root och ändra systemet). Docker är den enda
  förkunskapen du själv sätter upp.

## Relation till resten
Installern är bara orkestreringen runt `make init` (wizarden, `WIZARD.md`) — den lägger till
"förkontroll + hämta koden" så att allt blir **ett** kommando. Allt annat (config-generering,
hemligheter, stacken) gör `make init` / `make up` / `make doctor`.

## Acceptanskriterier
- [ ] Ett kommando på en färsk Linux-maskin (med Docker) → körande instans.
- [ ] `--yes` ger oövervakad install för leverantör/CI utan frågor.
- [ ] Skriptet är auditbart; inspect-first-vägen dokumenterad.
- [ ] Stoppar med tydlig instruktion om Docker saknas; installerar det inte i smyg.
