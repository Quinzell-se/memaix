# Koppla in AI-klienter

Connector-URL är din instans publika URL (t.ex. `https://mcp.kundens-domän.se`). Lägg ALLTID in
den via tjänstens **webb** först — den synkar sedan till desktop och mobil.

## Claude (alla betalplaner)
Settings → Connectors → **Add custom connector** → URL → OAuth-login. Full **read/write**, ingen
läs-spärr. Synkar till iOS + desktop. Lägg minnesprotokollet i Claude Projects custom instructions.

## Mistral Le Chat (Free räcker för read/write)
Connectors → custom MCP-URL → OAuth. Read/write ingår även på Free (skriv kräver manuell
godkännande). ~25 medd/dag på Free; Pro höjer taket.

## ChatGPT
Kräver **Developer Mode** + custom connector via webben. **Plus/Pro = läs-bara.** Full read/write
kräver **Business** (min 2 säten).

## Perplexity (Pro/Max/Enterprise)
Connectors → custom MCP-URL. Pro+ kan skriva.

## Gemini
Konsumentappen saknar bekräftat skriv-stöd för egna remote-connectors. Skriv-MCP finns via Gemini
CLI och Gemini Enterprise.

## Read/write-matris

| AI | Lägsta plan för full read/write | Not |
|---|---|---|
| Claude | Pro | Ingen läs-spärr |
| Mistral Le Chat | Free | Skriv med manuell godkänning |
| Perplexity | Pro | — |
| ChatGPT | Business | Plus/Pro = läs-bara |
| Gemini | (CLI/Enterprise) | Appen ej bekräftad |
