# Licensiering — komponenter & vårt eget val

> **Brasklapp:** inte juridisk rådgivning. Licensval + dual-licensiering + CLA bör granskas av en
> OSS/IP-jurist innan kommersiell lansering. Verifiera varje komponents *aktuella* licens vid bygge
> (de ändras — Forgejo bytte t.ex. till GPLv3 2024).

## Komponenter vi bygger på (licensinventering)
| Komponent | Roll | Licens | Typ |
|---|---|---|---|
| **ory Hydra** | OAuth-server | Apache 2.0 | permissiv |
| **PostgreSQL** | DB (Hydra) | PostgreSQL License | permissiv |
| **Nextcloud** | kalender/filer | **AGPL-3.0** | stark copyleft (nätverk) |
| **Forgejo** (v9+) | git-forge | **GPL-3.0+** | copyleft |
| Gitea / GitLab CE | git-forge (alt) | MIT | permissiv |
| **Ollama** | lokal modell-runtime | MIT | permissiv |
| vLLM / cloudflared | serving / tunnel | Apache 2.0 | permissiv |
| restic / borg | backup | BSD | permissiv |
| MCP Python SDK, caldav, imap-tools, requests, pyyaml | gateway-deps | MIT/BSD/Apache | permissiva |
| Modeller: **Qwen, Gemma, Mistral** | lokal LLM | Apache 2.0 | permissiv |
| Modell: **Llama** | lokal LLM | Meta Community (ej OSI) | **användningsrestriktioner** |

## Den avgörande principen: aggregering ≠ derivat
- **Tjänster över nätverk/API ≠ derivatverk.** Nextcloud (AGPL) och Forgejo (GPL) körs som
  **separata containrar** vi pratar med över API — det skapar **inget derivat** och tvingar **inte**
  Memaix-koden till AGPL/GPL. **Vi kan välja vår egen licens fritt.**
- **Direkta bibliotek måste vara kompatibla.** Det vi *importerar* i gateway-koden (Python-libs) ska
  vara kompatibelt med vår licens → **håll direkta beroenden permissiva/LGPL**; importera inte ett
  GPL-*bibliotek* in i processen om vi inte vill vara GPL.
- **Distribuera inte modifierade copyleft-appar** utan att följa deras villkor. Vi **pullar images**
  (redistribuerar inte deras kod) → lätt. Modifierar vi Nextcloud/Forgejo och *distribuerar* → måste
  dela källa enligt deras licens.
- **Modell-licenser:** **Llama** har användningsrestriktioner (ej fri vid mycket stor skala) →
  föredra **Apache-modeller (Qwen/Gemma/Mistral)** som default för att slippa villkorskrångel.

## Vår egen kod — alternativ
| Licens | Skydd mot stängd fork/SaaS | Adoption/enterprise | Status |
|---|---|---|---|
| **AGPL-3.0** | Starkt (nätverks-copyleft) | Lägre (många företag bbobr AGPL) | OSI-öppen |
| Apache 2.0 / MIT | Inget (giganter kan stänga + sälja) | Högst | OSI-öppen |
| **BSL / SSPL** | Mycket starkt (förbjuder konkurrerande SaaS) | Medel | **Ej** OSI-öppen |
| Open-core + **dual-license** | Starkt + kommersiell väg | Hög | AGPL-kärna + kommersiell |

## Rekommendation
**AGPL-3.0 för kärnan + dual-licensiering + CLA/DCO + proprietära enterprise-moduler.**
- **AGPL-kärna** skyddar mot att någon tar Memaix, förbättrar privat och säljer en stängd managed-tjänst
  — och **linjerar med komponenterna** (Nextcloud AGPL, Forgejo GPL) och med integritets-/granskbarhets-
  varumärket (öppen kod *säljer* mot den målgruppen).
- **Dual-licensiering:** sälj en **kommersiell licens** till dem som inte kan acceptera AGPL (vanligt i
  storföretag). Kräver att du äger upphovsrätten → **CLA/DCO** från bidragsgivare, annars kan du inte
  relicensiera/sälja kommersiellt på community-kod.
- **BSL** bara om skydd av en framtida managed-SaaS är *viktigare* än "äkta öppen källkod" — men det
  offrar OSS-goodwillen som är en del av trust-positioneringen. Sannolikt fel för Memaix.

## Praktiska skyldigheter (oavsett val)
- **SBOM** + per-komponent-licensfiler + **NOTICE/attribution** (kopplar till supply chain, SECURITY.md).
- Full AGPL-text i `LICENSE` (vår kod) + namn på rättighetsinnehavare.
- Dokumentera bundlade komponenters licenser så en nedladdare ser hela bilden.

## Acceptanskriterier
- [ ] Direkta gateway-beroenden är permissiva/LGPL (inga GPL-libs in i processen oavsiktligt).
- [ ] Bundlade copyleft-appar (Nextcloud/Forgejo) körs som tjänster, ej länkade/modif-distribuerade.
- [ ] Vår kod: AGPL-3.0 + CLA/DCO på plats för dual-licensiering.
- [ ] SBOM + NOTICE listar alla komponenters licenser; Llama-restriktion flaggad.
- [ ] En OSS/IP-jurist har granskat dual-licens + CLA före kommersiell lansering.
