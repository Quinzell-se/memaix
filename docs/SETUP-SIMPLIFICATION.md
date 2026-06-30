# Förenkla installation, setup & config (för GitHub-nedladdare)

Kritiskt: vårt scaffold idag = **4 config-filer** (`brand`/`memaix`/`acl`/.env-`.example`) som ska
kopieras och **handredigeras**, + manuell secret-generering. Det är för mycket för någon som bara
klonar repot. Mål: från `git clone` till körande med **minimal handpåläggning**.

## Var friktionen sitter
- **4 config-filer** att kopiera + redigera för hand.
- **Manuell secret-generering** (`openssl rand …`).
- **Många förkunskaper** (Docker, domän, tunnel, OAuth, Nextcloud, LLM).
- **Oklart vad man gör efter clone.**

## De viktigaste greppen (prioriterade)
1. **Generera config — handredigera inte.** `make init` ställer **≤ 3 frågor** → skriver **all** config
   + **auto-genererade hemligheter**. Ingen kopiering av `*.example`, ingen `openssl`, ingen
   YAML-redigering i normalfallet.
2. **Sane defaults + preset.** Ändra på sin höjd 2–3 värden (domän, admin-mejl); allt annat defaultas.
   `profile: trial | solo | team` buntar resten.
3. **Krymp config-ytan: 4 filer → 1 (som man kanske rör).**
   - `brand` → **sektion** i `memaix.yaml` (defaultar till "Memaix").
   - `model` → **sektion** i `memaix.yaml` (bara server-side-lägen).
   - `acl` → **seedas av `init`** (ett demo-projekt, admin = owner); egen fil bara när man växer.
   - `.env` → **auto-genereras** av `init` (hemligheter), aldrig handskrivet.
   → Nedladdaren rör i normalfallet **noll filer** manuellt.
4. **En kommando att köra.** `docker compose up` / `make up` reser **hela** stacken — Hydra, Postgres,
   Nextcloud bundlade. Inget separat att installera utöver Docker.
5. **Containerisera alla beroenden.** Inget på värden utom Docker.
6. **Vänlig validering.** `make doctor` fångar fel tidigt med pekare till fixen.
7. **Börja smått (tiers).** Tier 0 = lokal **stdio-trial** (inget tunnel/OAuth/domän); uppgradera till
   remote (mobil/team) senare. Se nedan.
8. **En kort README-quickstart** — 3 kommandon, copy-paste.

## Mål-quickstart (det en nedladdare möter)
```
git clone … && cd memaix
make init      # ≤3 frågor → genererar config + hemligheter, seedar demo-projekt
make up        # reser hela stacken (bara Docker krävs)
make doctor    # grönt
```
Default = lokal trial (stdio, inget externt konto). `make go-remote` när du vill ha mobil/multi-user.

## Tre nivåer (grepp 7, kort)
- **Tier 0 — Prova-på:** lokal stdio-MCP som t.ex. Claude Desktop startar. Inget tunnel/OAuth/Hydra/
  domän. ~5 min, noll konton. Rätt sätt att *utvärdera*.
- **Tier 1 — Self-host:** lägg på tunnel + Hydra OAuth när du vill nå det från iOS / släppa in fler.
- **Tier 2 — Managed:** du installerar Tier 1 åt kund.

## Vad som ändras i scaffoldet (riktning)
- Slå ihop `brand`/`model` som **sektioner** i `memaix.yaml`; behåll `acl` separat men **seedad**.
- `make init` blir front-dörren (genererar allt); `*.example`-filerna blir referens, inte obligatorisk
  kopiering.
- `bootstrap.py` får `--trial` (stdio, ingen tunnel/Hydra/NC) och genererar hemligheter (redan delvis).

## Acceptanskriterier
- [ ] `make init` skriver all config + hemligheter; inga `*.example` att kopiera, ingen `openssl`.
- [ ] Normalfallet kräver att nedladdaren redigerar **noll** YAML manuellt.
- [ ] Hela stacken reses med ett kommando; bara Docker krävs.
- [ ] Trial igång < 5 min utan externa konton; uppgradera till remote utan omstart från noll.
- [ ] `make doctor` ger vänliga fel med fix-pekare.
