<!-- Brandnamnet "Memaix" är standard men white-label: byts i config/brand.yaml -->

# Memaix

**Bring your own AI. Own your memory.**

> En AI-agnostisk ingång till ett team-gemensamt minne — projektkunskap, personkunskap och
> utvecklingsbehov — plus en projektledaragent som håller koll på vad som ska göras, vem som gör vad,
> när, vilka beroenden som finns, och konsekvenserna om något inte görs i tid. **Hjärnan minns.
> Agenten agerar.**

Memaix är en självhostad, AI-agnostisk assistent-gateway. En enda connector gör vilken
MCP-kapabel AI som helst — Claude, ChatGPT, Mistral, Perplexity — till en **delad
affärsassistent** för ditt team. Projekt-baserad åtkomststyrning, git-versionerat minne och en
gemensam backlog. Datan ligger på din server. Du byter AI när du vill; minnet och arbetssättet
följer med.

> Det är inte "ännu en MCP-server". Det är assistent-lagret — minne, backlog, roller, onboarding —
> bakom en dörr.

## Varför Memaix

- **En connector, alla AI:er.** MCP är en öppen standard. Lägg in samma URL i Claude, ChatGPT,
  Mistral eller Perplexity. Ingen inlåsning.
- **Du äger datan.** Självhostad. Öppna standarder bakom: IMAP/SMTP (mejl), CalDAV (kalender),
  WebDAV (filer), git (minne). Inget lämnar din infrastruktur.
- **Team, inte bara individ.** En connector, flera personer, åtkomst per projekt (RBAC). En
  extern medarbetare låses till exakt ett projekt.
- **Minne som överlever.** AI:er glömmer mellan sessioner. Memaix ger ett delat, git-versionerat
  markdown-minne som varje AI läser vid start och skriver till — med historik och rollback.
- **Inbyggda arbetsflöden.** Gemensam backlog (fånga → utvärdera → besluta), onboarding genom
  intervju, portabel operating manual.

## Vad du kan göra

- Läsa och sammanfatta mejl, skapa utkast (skicka kräver manuellt godkännande).
- Hantera kalender — skapa, ändra, hitta lediga tider.
- Läsa och skriva filer i din molnlagring.
- Fånga idéer och feedback i en gemensam, poängsatt backlog per projekt.
- Ge varje AI samma minne och samma arbetssätt, oavsett tjänst.

## Snabbstart (självhostat)

```bash
git clone <ditt-memaix-repo> memaix && cd memaix
make init      # ≤3 frågor → genererar all config + hemligheter, seedar demo-projekt
make up        # reser hela stacken (bara Docker krävs)
make doctor    # grönt
```

Du redigerar **ingen** YAML och genererar **inga** hemligheter för hand — `make init` gör allt.
Default = lokal trial (stdio, inget externt konto). Vill du nå det från mobilen/teamet:
`make go-remote` (lägger tunnel + OAuth). Vilken AI ska driva det? → **[docs/CHOOSE-YOUR-LLM.md](docs/CHOOSE-YOUR-LLM.md)**.
Förenklingsplan: **[docs/SETUP-SIMPLIFICATION.md](docs/SETUP-SIMPLIFICATION.md)** · full guide: **[docs/INSTALL.md](docs/INSTALL.md)**.

## Dokumentation

Börja i **[docs/INDEX.md](docs/INDEX.md)** — innehållsförteckning i läsordning per roll.
Ska du **bygga** detta? Börja i **[HANDOFF.md](HANDOFF.md)** — hämta-hem + byggordning + v2-beslut.
Vilken **AI** ska driva Memaix? → **[docs/CHOOSE-YOUR-LLM.md](docs/CHOOSE-YOUR-LLM.md)** (beslutsguide).

| Dokument | Innehåll |
|---|---|
| [docs/INSTALL.md](docs/INSTALL.md) | Komplett installationsguide |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Hur det hänger ihop |
| [docs/SECURITY.md](docs/SECURITY.md) | Härdning + kända fallgropar (OAuth, Cloudflare) |
| [docs/WHITE-LABEL.md](docs/WHITE-LABEL.md) | Byt namn, domän, branding |
| [docs/AI-CLIENTS.md](docs/AI-CLIENTS.md) | Koppla in Claude, ChatGPT, Mistral m.fl. |
| [docs/MCP-API.md](docs/MCP-API.md) | Verktygsreferens — vad man kan göra via MCP |
| [docs/SERVICE-PROVIDERS.md](docs/SERVICE-PROVIDERS.md) | Sälja installation/hosting till kunder |
| [docs/BUILD.md](docs/BUILD.md) | Bygg-spec för gateway-implementationen |

## Licens

AGPL-3.0. Du får köra, ändra och hosta fritt. Ändringar du distribuerar (inkl. som nättjänst)
måste hållas öppna. Du får sälja installation och hosting som tjänst. Se [LICENSE](LICENSE).

## Status

Tidigt. Gatewayens implementation byggs mot specen i `docs/BUILD.md`. Granska alltid AI:ns
arbete innan något skickas eller publiceras.
