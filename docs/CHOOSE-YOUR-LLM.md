# Vilken LLM ska du använda? — guide för dig som laddat ner Memaix

Du har Memaix igång. Nu: vilken AI driver den, och hur kopplar du in den? Memaix är AI-agnostiskt —
du väljer. Den här guiden tar dig till rätt väg på 30 sekunder. Bakgrund: `ACCESS-MODES.md`.

## Beslutsträd
1. **Har du redan Claude / ChatGPT / Mistral?** → **Läge 1: BYO AI.** Lägg in connectorn i din
   AI-app. Minst setup, bäst kvalitet. (`AI-CLIENTS.md`)
2. **Inget AI-abonnemang, vill komma igång billigt med hög kvalitet?** → **Läge 2: Memaix-egen chatt
   + API-nyckel.** Skaffa en API-nyckel, klistra in i config. Betalar per token.
3. **Får ingen data lämna huset (GDPR/sekretess)?** → **Läge 3: lokal modell.** Kräver GPU. Inget
   lämnar boxen. (`LOCAL-MODEL.md`)
4. **Vill bara ha planering/kunskapsbas, ingen AI?** → **Läge 4: deterministiskt GUI.** Ingen LLM.

## Rekommendation per situation
| Din situation | Läge | Modell att välja | Hur du kopplar |
|---|---|---|---|
| Har Claude/ChatGPT/Mistral | 1 BYO | **Claude** (bäst agentiskt) · **Mistral Le Chat** (billigast, free funkar) · **ChatGPT Business** (för skriv) | connector-URL i AI-appen |
| Inget abonnemang, vill starta billigt + bra | 2 API | en **frontier-modell** (Claude/GPT/Mistral) — eller **OpenRouter** = en nyckel, alla leverantörer | `model`-block i `memaix.yaml` + nyckel i `.env` |
| Ingen data får lämna huset | 3 Lokal | 24 GB: **Qwen3-Coder-30B / Mistral Small 4** · 11 GB: **xLAM-2-8B / Gemma 3 12B** (dogfood) | `endpoint` mot Ollama/vLLM |
| Bara planering/kunskap | 4 GUI | — (ingen) | — |

## Modell-config (för server-side lägen 2/3/5)
BYO AI (läge 1) behöver **inget** av detta — modellen bor i din AI-app. För server-side lägen:

> Du behöver normalt inte skriva blocket för hand: **setup-wizarden** (frågan "Vilken AI?")
> skriver det vid installation, och **/app/admin → System → AI-modell** ändrar det i drift
> (admin + MFA; nyckeln lagras som `file:`-ref i `config/secrets/`, aldrig i YAML).

```yaml
# config/memaix.yaml
model:
  provider: anthropic          # anthropic | openai | openrouter | mistral | google | openai-compatible | ollama | vllm
  name: "claude-sonnet-4-x"    # via openrouter: "anthropic/claude-..." osv
  api_key_ref: LLM_API_KEY     # moln-API → .env; utelämna för lokal
  endpoint: ""                 # openrouter/openai-compatible: bas-URL; lokal: http://localhost:11434
```

## Ärlig kvalitets-/kostnadsordning
- **Kvalitet:** frontier (Claude/GPT/Mistral Large) > stark öppen 32B > liten 7–14B.
- **För PM-agenten gäller:** *tillförlitligt verktygsanrop* väger tyngre än råsmarthet — vilken
  frontier-modell som helst duger; lokal kräver en hög-BFCL-modell (`LOCAL-MODEL.md`).
- **Kostnad:** BYO = ditt abonnemang · API = per token · lokal = hårdvara, inga tokens · GUI = inget.
- **Integritet:** lokal (läge 3) = inget lämnar boxen; BYO/API = data går till AI-leverantören.

## Vad som funkar idag vs planerat
- **Läge 1 (BYO AI)** är den direkta vägen — fungerar så fort gatewayen står (MCP-connector).
- **Läge 2/3/4** (Memaix-egen chatt, lokal modell, GUI) är planerade byggsteg ovanpå samma verktyg/data.

## Kort råd
- Har du redan en AI → **BYO (läge 1)**, klart på minuter.
- Vill du slippa abonnemang men ha kvalitet → **API-nyckel (läge 2)**.
- Känslig data → **lokal modell (läge 3)**.
- Bara planering → **GUI (läge 4)**.
