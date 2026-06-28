# Förenkla setup — friktionsanalys & plan

Setup är planens svagaste punkt. Den här doc:en är kritisk om var tröskeln sitter och hur vi kapar
den, så en nedladdare kommer igång på minuter — inte en kväll. Kompletterar `WIZARD.md` / `INSTALL.md`.

## Var friktionen faktiskt sitter (ärligt)
1. **Tunnel + domän** (Cloudflare-tunnel, DNS, Bot Fight av) — manuella konsol-steg.
2. **OAuth-server (Hydra) + Postgres** — en komponent till att konfigurera.
3. **Nextcloud** — tung, provisionering.
4. **OAuth-app-registrering** (Gmail/M365) — manuella steg, går ej att fullautomatisera.
5. **Tre config-filer** + hemligheter.
6. **Koppla connectorn** i AI-appen.

> Allt detta behövs **bara för det remote (mobil/multi-user) läget.** Det är nyckeln till förenkling.

## Princip: matcha ansträngning mot behov — tre nivåer

**Tier 0 — Prova-på (lokalt, desktop).** Kör Memaix som en **lokal stdio-MCP-server** som t.ex.
Claude Desktop startar. **Inget** tunnel, **ingen** Hydra/OAuth-server, **ingen** domän, **ingen**
publik exponering. SQLite + git-minne, filer, backlog fungerar direkt. Mejl/kalender valfritt (lokala
IMAP-uppgifter). **Igång på ~5 minuter, noll externa konton.** Det här är den enskilt största
förenklingen — och rätt sätt att *utvärdera* Memaix.

**Tier 1 — Self-host (mobil/team).** "Uppgraderingen": lägg på tunnel + Hydra OAuth när du vill nå
det från iOS eller släppa in flera personer. Det är då (och bara då) det svåra behövs.

**Tier 2 — Managed.** Du som leverantör installerar Tier 1 åt kunden.

## De största förenklingsgreppen
1. **Tier 0 stdio-läge** — droppar tunnel/OAuth/Hydra/domän för utvärdering. (Störst vinst.)
2. **Opinionerade defaults + en-kommando quickstart** — minimera val. Bundlad Nextcloud, bundlad
   Hydra (bara Tier 1), SQLite, draft-only, ett demo-projekt seedat.
3. **Progressiv setup** — få en fungerande assistent (minne + backlog + filer) **först**; lägg
   mejl/kalender/tunnel **senare**. Inget tvång att fixa allt på en gång.
4. **Quick-tunnel för trial av remote** — Cloudflare `trycloudflare.com` ger en tillfällig publik URL
   utan konto/DNS; Tailscale Funnel som alternativ. (Ej för produktion, men noll-friktion för test.)
5. **Skjut upp OAuth-app-registrering** (Gmail/M365) — börja utan dem; lägg till när behov finns.
6. **Profiler** — `profile: trial | solo | team` buntar defaults så wizarden frågar ≤ 3 saker.

## Konkret quickstart-flöde (mål)
```
git clone … && cd memaix
make trial          # bundlad allt lokalt, stdio-MCP, ett demo-projekt seedat
# → skriver ut hur du lägger till den i Claude Desktop (lokal MCP), klart.
```
Vill du sedan nå det från mobilen: `make go-remote` (lägger tunnel + Hydra, kör doctor).

## Vad som ändras i specen
- **WIZARD/INSTALL:** inför **Tier 0 stdio-trial** före de remote-stegen; gör domän/tunnel/OAuth till
  *valfria, senare* steg — inte förstagångskrav.
- **Config:** `profile`-fält som sätter defaults; minimera obligatoriska fält.
- **bootstrap:** `--trial` (stdio, ingen tunnel/Hydra/NC) och `--no-nextcloud` redan planerat.

## Acceptanskriterier
- [ ] Trial igång på < 5 min, noll externa konton, ingen tunnel/OAuth.
- [ ] Quickstart frågar ≤ 3 saker (resten defaultas, kan ändras efteråt).
- [ ] Mejl/kalender/tunnel kan läggas till **efter** att assistenten redan fungerar.
- [ ] `make go-remote` tar en trial-instans till mobil-/multi-user utan omstart från noll.
