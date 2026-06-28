# Lokal modell — utvärdering (åtkomstläge 3)

Konkret bedömning av att köra Memaix på en **lokal öppen modell** (inget lämnar boxen). Hör ihop med
`ACCESS-MODES.md` läge 3 och integritetsargumentet i `LEGAL.md`. Dagsläge: juni 2026 — verifiera
aktuell modell-/benchmarkstatus vid bygge.

## Nyckelinsikt: baren är LÄGRE för Memaix
Eftersom Memaix lägger **matematiken i kod** (allokering, kritisk linje, what-if — `PM-PLANNING-
ENGINE.md`), behöver den lokala modellen *inte* vara en frontier-resonerare. Den ska bara:
1. fånga avsikt → strukturerad input,
2. **anropa `pm_*`-verktygen korrekt** (tillförlitligt function-calling),
3. återge resultatet i text.

Det är en **smalare** uppgift än en "gör-allt"-agent. Därför är lokala modeller realistiska *här*,
där de skulle vara för svaga för öppen agentisk kodning. Determinismgränsen räddar kvaliteten.

## Vad modellen ska väljas på
**Function-calling-tillförlitlighet**, inte allmän "smarthet". Välj efter
**Berkeley Function-Calling Leaderboard (BFCL)**-poäng + JSON/verktygs-läge. En modell som
hallucinerar verktygsargument eller missar att anropa verktyg **bryter loopen** — det är den enda
riktiga risken.

## Rekommenderade modeller (juni 2026)
| Klass | Modeller | Lämplighet |
|---|---|---|
| **Sweet spot (30–32B)** | **Qwen3-Coder-30B** (toppar BFCL för verktyg), **Mistral Small 4** (production-agenter, function-calling, JSON) | Bäst pris/kvalitet för Memaix; en GPU räcker |
| Tyngre (70B+) | Llama-/Qwen-70B-klass | Bättre omdöme; dubbel-GPU |
| Frontier-öppna (stora) | GLM-5.2, DeepSeek V4, Kimi K2.6, Qwen 3.6 Plus | Frontier-nära, men för stora för blygsam hårdvara |
| Små (≤13B) | 7–13B | OK för sammanfattning; **för svaga** för agent-omdöme/verktyg — undvik som motor |

## Hårdvara (Q4_K_M-kvantisering)
| Modell | VRAM (Q4) | Exempel-GPU | Ungefärlig kostnad |
|---|---|---|---|
| 7B | 4–6 GB | vilken modern GPU | låg |
| 13B | 8–10 GB | RTX 4070/4080 | låg–medel |
| **32B** | **~20–24 GB** | **1× RTX 3090/4090 (24 GB)** | ~$800–2 000 (begagnad–ny) |
| 70B | 48 GB+ | 2× 24 GB eller 1× 48 GB | $$$ |

- **KV-cache växer med kontextlängd** → långa projekt­historiker äter VRAM. Vår **retrieval-disciplin
  ("dumpa aldrig", `SAFETY.md`) håller kontexten liten** → modest VRAM. Bra synergi.
- **Servering:** **Ollama** (GGUF) för litet team/enkel drift; **vLLM** (AWQ/GPTQ) för fler samtidiga
  användare/genomströmning.

## Ärlig dom
- **Realistiskt** för Memaix tack vare determinismgränsen: en **32B med hög BFCL-poäng (Qwen3-Coder-30B
  / Mistral Small 4) på en 24 GB-GPU** är den pragmatiska startpunkten.
- **Men testa innan löfte.** Bygg en liten **eval-svit** som kör typiska flöden (fånga avsikt →
  `pm_allocate`/`pm_whatif` → korrekta argument → vettig återgivning) mot kandidatmodellen. Verktygs-
  tillförlitligheten är det som avgör, inte demo-känslan.
- **Kvalitetstak:** öppna modeller är fortfarande svagare än Claude/GPT på *fritt* resonemang. För
  Memaix spelar det mindre roll (motorn räknar), men för riktigt öppna frågor märks skillnaden.

## Kostnadsbild
- **Lokal:** engångs hårdvara (~$800–2 000 för 32B-klass) eller en moln-GPU (~$0,5–2/tim). **Inga
  per-token-kostnader.** Inget lämnar boxen.
- Jämför mot API-läget (läge 2): per-token, bättre kvalitet, men data → leverantör.

## Rekommendation
Erbjud lokal modell som **integritets-maximalt** alternativ för reglerade/känsliga kunder. Standardisera
på en **32B med topp-BFCL** + Ollama (litet team) eller vLLM (flera användare). **Kräv en pass i
eval-sviten** innan en kund körs skarpt på lokal modell. För kunder utan integritetskrav: läge 2
(API) ger högre kvalitet billigare att komma igång.

## Att verifiera vid bygge
- [ ] Aktuell BFCL-topplista för 30–32B-modeller (fältet rör sig snabbt).
- [ ] Eval-svit: verktygsanrop-tillförlitlighet mot `pm_*` och kärnverktygen.
- [ ] VRAM-budget vid faktisk kontextlängd (KV-cache) med retrieval på.
- [ ] Ollama vs vLLM utifrån antal samtidiga användare.
