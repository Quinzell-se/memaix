<!-- Brandnamnet "Memaix" är standard men white-label: byts i config/brand.yaml -->

# Memaix

**Bring your own AI. Own your memory.**

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
cp .env.example .env                         # fyll i hemligheter
cp config/brand.example.yaml   config/brand.yaml
cp config/memaix.example.yaml  config/memaix.yaml
cp config/acl.example.yaml     config/acl.yaml
# redigera config/* — domän, tunnel, projekt, användare, backends
make install                                 # bootstrap: containrar + Nextcloud-provisionering + vault-seed
```

`make install` startar containrarna, provisionerar Nextcloud automatiskt från `acl.yaml`
(användare, app-lösenord, kalendrar) och seedar minnesvaulten. Har du egen backend:
`make install-no-nextcloud`. Lägg sedan in din publika URL som custom connector i din AI
(se `docs/AI-CLIENTS.md`).
Full guide: **[docs/INSTALL.md](docs/INSTALL.md)**.

## Dokumentation

Börja i **[docs/INDEX.md](docs/INDEX.md)** — innehållsförteckning i läsordning per roll.
Ska du **bygga** detta? Börja i **[HANDOFF.md](HANDOFF.md)** — hämta-hem + byggordning + v2-beslut.

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
