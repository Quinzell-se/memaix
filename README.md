<!-- Brandnamnet "Memaix" är standard men white-label: byts i config/brand.yaml -->

# Memaix — self-hosted AI assistant gateway

**Bring your own AI. Own your memory.**

En enda connector-URL gör vilken MCP-kapabel AI som helst — Claude, ChatGPT, Mistral, Perplexity
— till en delad assistent för ditt team. Projekt-baserad åtkomststyrning, git-versionerat minne
och en gemensam backlog. Datan stannar på din server.

```
git clone <detta-repo> memaix && cd memaix && make init
```

> Bara Docker krävs. Wizarden ställer 3–4 frågor och genererar all config + hemligheter.
> En HTML-sida öppnas med exakta instruktioner för att koppla in din AI.

---

## Vad är det?

Memaix är ett **assistent-lager** — minne, backlog, roller, onboarding — bakom en MCP-dörr.

- **En connector, alla AI:er.** MCP är en öppen standard. Samma URL funkar i Claude, ChatGPT, Mistral och fler.
- **Du äger datan.** Självhostat. Öppna standarder: IMAP/SMTP, CalDAV, WebDAV, git. Ingen inlåsning.
- **Team, inte bara individ.** RBAC per projekt — en extern kan låsas till exakt ett projekt.
- **Minne som överlever sessioner.** SQLite + git-versionerade vaults med rollback.
- **Inbyggda arbetsflöden.** Backlog, onboarding-intervju, portabel operating manual.

---

## Kom igång

**Förutsättning:** Docker installerat.

```bash
# 1. Klona
git clone <detta-repo> memaix && cd memaix

# 2. Wizard — genererar config, hemligheter, seedar vaults, startar stacken
make init

# 3. Verifiera
make doctor
```

Wizarden öppnar `setup-complete.html` med din connector-URL och steg-för-steg för
Claude, ChatGPT, Mistral med flera.

**Lokal trial** (inget konto, inget tunnel, ~5 min): välj spår 1 i wizarden.
**Mobil/team**: välj spår 2 — lägger till Cloudflare-tunnel och OAuth.

---

## Vad kan du göra

| Verktyg | Vad AI:n kan göra |
|---|---|
| `email_*` | Läsa, söka och skriva mejlutkast (skicka kräver godkännande) |
| `calendar_*` | Lista, skapa, hitta lediga tider |
| `files_*` | Läsa och skriva filer i din molnlagring |
| `memory_*` | Läsa och skriva delat minne med git-historik och rollback |
| `backlog_*` | Fånga idéer, poängsätta, besluta |
| `whoami` | Visa identitet och projektbehörigheter |

---

## Koppla in din AI

Steg-för-steg för varje tjänst, abonnemangskrav och OAuth-info finns i
**[docs/AI-CLIENTS.md](docs/AI-CLIENTS.md)**.

Snabbversion:

| AI | Lägsta plan | Steg |
|---|---|---|
| Claude (claude.ai) | Pro ($20/mån) | Settings → Connectors → Add custom connector |
| Mistral Le Chat | **Free** | Settings → Connectors |
| ChatGPT | Plus ($20/mån) | Settings → Connectors/Tools |
| Perplexity | Pro ($20/mån) | Settings → AI Tools |
| Cursor | **Gratis** | Settings → MCP → HTTP |
| VS Code + Copilot | Copilot ($10/mån) | Command Palette → Add MCP Server |

---

## Exponering — hur når AI:n servern?

Sex alternativ dokumenterade i **[docs/EXPOSE.md](docs/EXPOSE.md)**:
Cloudflare Tunnel (rekommenderas), Caddy/nginx, underkatalog på befintlig server,
Tailscale Funnel, ngrok och Cloudflare Quick Tunnel.

---

## Dokumentation

| Dokument | Innehåll |
|---|---|
| [docs/INSTALL.md](docs/INSTALL.md) | Komplett installationsguide |
| [docs/EXPOSE.md](docs/EXPOSE.md) | Alla exponeringsalternativ |
| [docs/AI-CLIENTS.md](docs/AI-CLIENTS.md) | Koppla in Claude, ChatGPT, Mistral m.fl. |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Hur det hänger ihop (stack, RBAC, minne) |
| [docs/SECURITY.md](docs/SECURITY.md) | Härdning + kända fallgropar |
| [docs/MCP-API.md](docs/MCP-API.md) | Verktygsreferens |
| [docs/WHITE-LABEL.md](docs/WHITE-LABEL.md) | Byt namn, domän, branding |
| [docs/SERVICE-PROVIDERS.md](docs/SERVICE-PROVIDERS.md) | Sälja installation som tjänst |
| [docs/INDEX.md](docs/INDEX.md) | Alla docs i läsordning per roll |

---

## Licens

AGPL-3.0-or-later. Kör, ändra och hosta fritt. Ändringar du distribuerar (inkl. som nättjänst)
ska hållas öppna. Du får sälja installation och hosting som tjänst. Se [LICENSE](LICENSE).
