# Koppla in AI-klienter

Din Memaix connector-URL är `https://mcp.din-domän.se` (det du satte som `public_url` vid
`make init`). Den läggs in en gång på webben — synkar sedan till mobil och desktop.

Memaix använder **OAuth 2.1 med PKCE** för autentisering. Klienten måste stödja
OAuth-autentiserade remote MCP-servrar (inte bara localhost/stdio). Se kolumnen "OAuth" nedan.

---

## Snabb-matris

| Klient | Lägsta plan | OAuth remote MCP | Steg |
|---|---|---|---|
| **Claude** (claude.ai) | Pro ($20/mån) | ✓ | [→](#claude-claudeai) |
| **Claude Desktop** | Pro | ✓ HTTP | [→](#claude-desktop) |
| **Mistral Le Chat** | Free | ✓ | [→](#mistral-le-chat) |
| **Perplexity** | Pro ($20/mån) | ✓ | [→](#perplexity) |
| **ChatGPT** | Plus ($20/mån) | ✓ | [→](#chatgpt-openai) |
| **Cursor** | Hobby (gratis) | ✓ HTTP | [→](#cursor) |
| **VS Code + Copilot** | Copilot ($10/mån) | ✓ HTTP | [→](#vs-code-github-copilot) |
| **Gemini** (app) | Advanced ($20/mån) | Begränsad | [→](#gemini) |
| **Zed** | Gratis | ✓ HTTP | [→](#zed) |

> **OAuth vs HTTP**: "OAuth" = klienten hanterar hela OAuth-flödet (rekommenderat).
> "HTTP" = klienten skickar en statisk Bearer-token du genererar manuellt.

---

## Claude (claude.ai)

**Plan:** Pro, Max, Team eller Enterprise. Free stöder inte custom connectors.

1. Gå till **claude.ai** → klicka på ditt namn uppe till höger → **Settings**.
2. Välj fliken **Connectors** (eller "Integrations" beroende på version).
3. Klicka **Add custom connector**.
4. Klistra in din connector-URL: `https://mcp.din-domän.se`
5. Klicka **Connect** — webbläsaren öppnar en OAuth-login på din Memaix-instans.
6. Logga in med ditt admin-lösenord → klicka Godkänn.
7. Konnektorn visas som **Connected** ✓.

**Synk:** Connectors satta på webben synkar automatiskt till Claude iOS-appen och Claude Desktop.

**Prova:** Skriv "kör whoami i Memaix" i en ny konversation — ska returnera ditt användarnamn
och dina projekt.

**Tips:** Lägg till ett Projects system prompt med Memaix-instruktioner (se `vault-template/shared/assistant-manual.md`).

---

## Claude Desktop

**Plan:** Kräver Claude-prenumeration (Pro eller högre).

Claude Desktop stöder remote HTTP MCP med Bearer-token. Generera en token via Hydra:

```bash
# På servern — generera en långlivad access-token
docker exec memaix-hydra-1 hydra token client \
  --endpoint http://localhost:4445 \
  --client-id <ditt-client-id>
```

Eller enklare: lägg in connector via claude.ai webben (ovan) — Claude Desktop plockar upp den
automatiskt via kontosynken.

**Alternativt (manuell JSON):** Redigera `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "memaix": {
      "type": "http",
      "url": "https://mcp.din-domän.se",
      "headers": {
        "Authorization": "Bearer <din-token>"
      }
    }
  }
}
```

---

## Mistral Le Chat

**Plan:** Free räcker för att koppla in och läsa. Pro ($15/mån) höjer rate limits markant.

1. Gå till **chat.mistral.ai** → Settings → **Connectors** (eller "MCP Servers").
2. Klicka **Add connector** → välj "Custom MCP".
3. Ange URL: `https://mcp.din-domän.se`
4. Klicka **Connect** → OAuth-flöde öppnas → logga in på din Memaix.
5. Klart.

**Not:** Mistral är generellt snäll mot MCP-servrar — bra för att testa att konnektorn fungerar
utan att lägga pengar på ett Pro-konto.

---

## Perplexity

**Plan:** Pro ($20/mån) eller Enterprise.

1. Gå till **perplexity.ai** → inställningar → **AI Tools** eller **Connected services**.
2. Lägg till MCP-server → ange `https://mcp.din-domän.se`.
3. Följ OAuth-flödet.

> **Obs:** Perplexitys MCP-stöd är fokuserat på sökning/research-mode. Verktyg som `memory_write`
> och `backlog_add` fungerar men kan kräva att du ber Perplexity explicit använda dem.

---

## ChatGPT (OpenAI)

**Plan:** Plus ($20/mån) för personligt bruk; Team/Enterprise för organisation.

1. Gå till **chatgpt.com** → klicka på ditt namn → **Settings** → **Connectors** (eller "Tools").
2. Klicka **Add** → välj **Custom MCP server**.
3. Ange: `https://mcp.din-domän.se`
4. Välj autentiseringsmetod: **OAuth** (om tillgängligt) eller **API key** (Bearer-token).
5. Följ instruktionerna → logga in via OAuth-flödet på din Memaix.

> **Not:** ChatGPT kräver att servern stöder OAuth 2.0 med PKCE — vilket Memaix gör.
> UI:t för MCP-connectors varierar beroende på din plan och region.

---

## Cursor

**Plan:** Hobby (gratis) inkluderar MCP-stöd. Pro ($20/mån) för fler AI-tokens.

Cursor stöder HTTP MCP via config-filen — OAuth-flöde hanteras inte automatiskt, använd Bearer-token.

**Generera token:** Logga in på din Memaix via webbläsaren (`https://mcp.din-domän.se/oauth2/auth...`)
och kopiera access-token från OAuth-svaret, eller extrahera den ur claude.ai om du redan kopplade
dit.

Redigera `.cursor/mcp.json` (global) eller `.mcp.json` (projektspecifik):

```json
{
  "mcpServers": {
    "memaix": {
      "url": "https://mcp.din-domän.se",
      "headers": {
        "Authorization": "Bearer <din-access-token>"
      }
    }
  }
}
```

Eller via Cursor UI: **Settings → MCP → Add server** → HTTP → klistra in URL och token.

---

## VS Code + GitHub Copilot

**Plan:** GitHub Copilot Individual ($10/mån) eller Business ($19/user/mån).

MCP-stöd i VS Code kräver Copilot-tillägg v1.250+ (maj 2025+).

1. Öppna Command Palette (`Cmd+Shift+P`) → **GitHub Copilot: Add MCP Server**.
2. Välj **HTTP** → ange URL: `https://mcp.din-domän.se`
3. Välj autentisering: **Bearer token** → klistra in din Memaix-token.
4. Spara — servern visas under **Copilot Chat → Tools**.

Alternativt, redigera `.vscode/mcp.json`:

```json
{
  "servers": {
    "memaix": {
      "type": "http",
      "url": "https://mcp.din-domän.se",
      "headers": {
        "Authorization": "Bearer <din-access-token>"
      }
    }
  }
}
```

---

## Gemini

**Plan:** Google One AI Premium ($20/mån) för Gemini Advanced; Gemini Enterprise för organisation.

Gemini-appen har begränsat MCP-stöd för tredjepartsservrar. Det tillförlitligaste sättet:

**Via Gemini CLI** (gratis, open source):
```bash
npm install -g @google/gemini-cli
gemini mcp add memaix https://mcp.din-domän.se --auth bearer --token <din-token>
gemini chat
```

**Via Google AI Studio** (aistudio.google.com):
Experimentellt stöd för MCP-servrar under Tools. Flödet liknar ChatGPT ovan.

> Gemini-appens inbyggda MCP-stöd för OAuth remote-connectors är under aktiv utveckling (2026).
> Kolla Googles release notes för senaste status.

---

## Zed

**Plan:** Gratis (open source-editor).

Zed har inbyggt MCP-stöd via `settings.json`:

```json
{
  "context_servers": {
    "memaix": {
      "command": {
        "path": "npx",
        "args": ["-y", "mcp-remote", "https://mcp.din-domän.se"]
      }
    }
  }
}
```

`mcp-remote` (npm-paket) hanterar OAuth-flödet och token-caching lokalt. Första gången öppnas
en webbläsare för OAuth-login.

---

## Felsökning

**"Authorization failed" / "ofid_..."**
Vanligaste orsaker och fix → se [SECURITY.md](SECURITY.md) och [EXPOSE.md](EXPOSE.md).

**Klienten stöder inte OAuth**
Generera en token manuellt och använd Bearer-header (se Claude Desktop / Cursor ovan).

**Klienten hittar inte verktygen**
Kör `whoami` i klienten för att bekräfta att konnektorn är aktiv. Om det misslyckas: kontrollera
att `public_url` matchar den URL du angett i klienten (inklusive protokoll, utan avslutande slash).

**Rate limit**
Standard: 60 req/min per användare, 120 req/min per projekt. Konfigurerbart i `memaix.yaml`.
