# Kallstart & import

Det största **adoptionshindret** (OPEN-GAPS #10–11). En tom instans = "återskapa allt" = ingen
börjar. Memaix måste kunna **suga in befintlig data** och göra sig nyttigt på minuter.

## Importkällor → mål
| Källa | Importeras till |
|---|---|
| Jira / Asana / Linear / Trello / **CSV** | backlog-items (med status/prioritet där det går) |
| Google Docs/Drive, Markdown, Notion-export | projektminne (kunskapsnoteringar) |
| Mejltrådar (befintlig inkorg) | sammanfattade noteringar i minnet (ej råa dumpar) |
| Personer (IdP / CSV) | `acl.yaml`-användare + projekt-grants |

## Hur (`memaix import`)
- `memaix import <källa> --project <p>` per källa → mappar till items/minne/personer.
- **Förhandsvisning innan commit** — människan godkänner mappningen (inga överraskningar).
- **Idempotent** — kör om utan dubbletter (kopplar till idempotensnycklar, SAFETY.md).
- **Retrieval-vänligt** — mejl/dokument *sammanfattas och indexeras*, dumpas inte råa (SAFETY.md §6).

## Kallstarts-mallar
Projekt-mallar som seedar struktur direkt: `mjukvaruprojekt`, `byråkund`, `konsultuppdrag`,
`internt-team`. Väljs i wizarden (`profile`) → backlog-kategorier, playbook och RAID-skelett finns
från start.

## Förstagångs-upptäckbarhet
- **First-run-exempel:** "Så här kan jag hjälpa dig" med 3–5 konkreta saker att prova.
- **`/memaix:help`** — visar förmågor i sammanhang (vad finns, vad kan jag fråga).
- Onboarding-intervjun (redan specad) fyller personprofilen samtidigt.

## Acceptanskriterier
- [ ] Minst en import-källa (CSV) → backlog fungerar med förhandsvisning + idempotens.
- [ ] Kallstarts-mallar seedar en användbar struktur utan manuellt arbete.
- [ ] Mejl/dokument importeras som sammanfattningar, inte råa dumpar.
- [ ] Ny användare ser konkreta exempel + `/memaix:help` vid första körning.
