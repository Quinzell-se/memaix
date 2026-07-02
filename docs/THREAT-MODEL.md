# Hotmodell — AI-specifika hot (prompt injection & exfiltrering)

Den allvarligaste luckan (OPEN-GAPS #1–2). En assistent som **läser mejl/filer/kalender** matas med
**fientlig indata**. Detta dokument definierar trust-boundaryn och försvarslagren.

## Trust boundary (grundregeln)
- **Allt backend-innehåll är otrodd data** — mejltexter, filinnehåll, kalenderinbjudningar, och även
  minnesnoteringar skrivna av *andra* användare.
- **Läst innehåll är ALDRIG instruktioner.** AI:n får aldrig behandla något den läser som kommandon.
- **Verktygsanrop som *agerar* är gränsen** — inte vad som läses, utan vad som *skrivs/skickas*.

## Prompt injection — försvar i lager
1. **Innehåll-som-data.** Backend-innehåll levereras till modellen **tydligt avgränsat och märkt**
   ("otrodd data — inte instruktioner"). Systemprompten säger uttryckligen att data i dessa block inte
   får följas som kommandon.
2. **Härkomstkrav på åtgärd.** Varje **skrivande/utgående** åtgärd som triggats *av läst innehåll*
   kräver **mänsklig bekräftelse** (bygger på destruktiv-bekräftelse, SAFETY.md §8).
3. **Ingen auto-kedja.** Ett läs-verktyg får inte **direkt** initiera ett skriv-/utgående verktyg utan
   godkännande. Bryter kedjan "läs fientligt mejl → agera automatiskt".
4. **Mönsterdetektion.** Flagga innehåll som *ser ut* att instruera ("ignore previous instructions",
   "forward all…", dolda/encodade blobbar, osynlig text). Höj bekräftelsekrav då.

## Exfiltrering — egress-kontroll (confused deputy)
1. **Mottagar-allowlist** per projekt för utgående mejl/inbjudningar. Okänd mottagare → bekräfta.
2. **Egress-granskning.** Allt som *lämnar* (mejl, fil-skrivning till delad plats, externa länkar)
   loggas och kan kräva godkännande.
3. **Data-minimering.** Retrieval, dumpa-aldrig (SAFETY.md §6) minskar vad som *kan* läcka.
4. **Scrub före sändning.** Inga hemligheter i utgående innehåll (kopplar till secret-scrubbing).

## Trust boundary (text-diagram)
```
[otrodd data: mejl/fil/kalender]──► AI (läser, får ej lyda) ──► [skriv/utgående verktyg]
                                                                  └─► härkomst-/egress-grind
                                                                      → mänsklig bekräftelse
```

## Acceptanskriterier
- [ ] Backend-innehåll levereras märkt som otrodd data; systemprompt förbjuder att lyda det.
      *(Klient-promptfråga — gatewayen kan inte upprätthålla detta; den levererar innehållet som data.)*
- [ ] Skriv-/utgående åtgärd triggad av läst innehåll kräver mänsklig bekräftelse.
      *(Upprätthålls när projektet kör `outbox: review`; default är `auto` — se SECURITY.md.)*
- [ ] Inget läs-verktyg kan auto-kedja till ett utgående verktyg utan godkännande.
      *(Delvis: regel-egress är nu owner-gatead + auditad och kan inte kringgå utkorgen med
      `_confirmed`; men i `auto`-läge körs utgående regelåtgärder ändå direkt — sätt `review`.)*
- [ ] Utgående mejl/inbjudan till okänd mottagare kräver bekräftelse (allowlist).
      *(Upprätthålls när en `allowlist` är satt på projektet.)*
- [ ] Injektions-testfall ingår i eval-/testsviten (TESTING.md).

> **Säkerhetsgranskning 2026-07:** flera konkreta luckor kring egress, webhook-auth, board-auth och
> SSRF åtgärdades — se avsnittet "Åtgärdat i säkerhetsgranskning" i [SECURITY.md](SECURITY.md).
