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

## Fler licensalternativ (hela menyn)
**OSI-öppna:**
- **MIT / BSD** — permissiv; gör nästan vad som helst, behåll notisen. Max adoption, noll skydd.
- **Apache 2.0** — permissiv + patentgrant + NOTICE-krav. Företagsvänlig permissiv.
- **MPL-2.0** — *fil-nivå*-copyleft: ändrar du MPL-filer delas de; får kombineras med proprietärt. Mellanläge.
- **LGPL** — biblioteks-copyleft: länka fritt, dela ändringar i själva biblioteket.
- **GPL-3.0** — stark copyleft men *bara vid distribution* → "SaaS-luckan" (modifierad GPL som tjänst behöver ej delas).
- **AGPL-3.0** — GPL + nätverksklausul som stänger SaaS-luckan. (Vårt val.)
- **EUPL-1.2** — EU:s copyleft, AGPL-likt, flerspråkigt, interop-vänligt. Värt en titt givet EU/integritets-vinkeln.

**Source-available (ej OSI-öppna):**
- **BSL 1.1** — källa öppen, konkurrerande/produktionsbruk begränsat i N år (oftast 4) → konverterar sen till öppen (Apache). HashiCorp/Sentry/MariaDB.
- **FSL (Functional Source License)** — lättare BSL; konverterar till MIT/Apache efter ~2 år, begränsar konkurrerande kommersiell användning under tiden.
- **Elastic License 2.0** — får ej erbjudas som managed-tjänst; enklare än SSPL.
- **SSPL** — AGPL-plus: erbjuder du det som tjänst måste *hela din stack* öppnas. Aggressivt, kontroversiellt, ej OSI.

**+ Kommersiell/proprietär** — för dual-licens-försäljningen och enterprise-modulerna.

**Realistisk kortlista för Memaix:** AGPL-3.0 (kärna) · EUPL-1.2 (EU-vinkeln) · BSL/FSL (om SaaS-skydd
väger tyngre än OSS-renhet) · alltid med **dual-license** ovanpå.

## De tre artefakterna i praktiken
Minnesregel: **rättigheter du samlar in / ger ut / hedrar.**

1. **CLA/DCO — rättigheter du *samlar in* från bidragsgivare.**
   - **DCO:** en `Signed-off-by`-rad per commit; bidragsgivaren intygar att de får bidra koden. Lätt,
     ingen rättighetsöverföring (Linux-kärnan kör DCO).
   - **CLA:** bidragsgivaren ger *dig* rätt att även **relicensiera** deras kod → det är detta som gör
     **dual-licensiering** möjlig. Utan CLA behåller varje bidragsgivare sin upphovsrätt under AGPL och
     du kan **inte** sälja deras delar kommersiellt.
   - **I praktiken:** vill du ha dual-license-affären → samla **CLA från dag ett** (verktyg: CLA
     Assistant-bot på PR). Retroaktivt är nästan ogörligt. Ingen dual-license-plan → DCO räcker.

2. **LICENSE — rättigheter du *ger ut* till världen.**
   - `LICENSE`-fil i repo-roten med **hela AGPL-3.0-texten** (ej bara en notis) + din copyright-rad,
     plus `SPDX-License-Identifier: AGPL-3.0-or-later` i källfilerna. Utan full text + tydlig
     innehavare är licensen otydlig och svår att hävda.

3. **SBOM + NOTICE — rättigheter du *hedrar* hos komponenterna.**
   - **SBOM:** maskinläsbar lista över varje beroende + version + licens (SPDX/CycloneDX), genererad i
     CI (Syft/cdxgen). Hittar licenskonflikter, svarar på sårbarheter, krävs allt oftare av
     företags-/myndighetsköpare.
   - **NOTICE/attribution:** permissiva licenser (Apache/MIT/BSD) **kräver att du behåller deras
     copyright-notiser** vid distribution. En `NOTICE`/`THIRD-PARTY-LICENSES`-fil samlar dem. Apache 2.0
     kräver uttryckligen att NOTICE förs vidare — juridisk skyldighet, inte artighet.

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
