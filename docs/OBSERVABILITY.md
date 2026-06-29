# Observability — drift-insyn

Hur man ser att en körande instans är frisk, snabb och inte missbrukad — kontinuerligt, inte bara
vid en doctor-körning. Ett av spåren från granskningarna (`REVIEW-RESPONSE.md`).

## Tre ben
- **Strukturerade loggar** (JSON) — händelser och fel, med korrelations-id.
- **Metrics** — siffror över tid via en `/metrics`-endpoint (Prometheus-format).
- **Traces** (valfritt, senare) — följ ett anrop genom gateway → adapter → backend (OpenTelemetry).

## Observability ≠ audit ≠ doctor
- **Audit:** "vem gjorde vad" — säkerhet/compliance, oföränderligt (SAFETY.md/ENTERPRISE.md).
- **Observability:** "är systemet friskt och snabbt" — drift/felsökning, för operatören.
- **Doctor:** ögonblicksbild ("rätt konfigurerat nu?"). Observability: kontinuerligt ("hur har det
  betett sig?"). `/health` är den lätta, ständiga liveness/readiness-kollen; doctor är den djupa.

## Kärn-metrics
| Metric | Typ | Säger |
|---|---|---|
| `up` / `/health` | gauge | gateway/Hydra/Nextcloud/backends uppe |
| `tool_calls_total{tool,project,status}` | counter | användning + felandel per verktyg |
| `tool_latency_seconds{tool,backend}` | histogram | hur snabbt/trögt per backend |
| `backend_errors_total{backend,type}` | counter | var det går sönder |
| `rate_limit_hits_total` / `budget_exhausted_total` | counter | missbruk/skenande AI |
| `circuit_state{backend}` | gauge | öppen/halv/stängd |
| `vault_write_queue_depth` | gauge | mättnad i skrivkön |
| `tokens_used{project,user}` | counter | kostnad/förbrukning |
| `accounts_needs_relink` | gauge | utgångna per-användar-OAuth-token |

## Loggar — vad som loggas (och inte)
- Strukturerad JSON, nivåer, **korrelations-id** per anrop, `user` + `project`.
- Per verktygsanrop: vem, vilket verktyg, projekt, resurs-*referens*, status, varaktighet.
- **Aldrig innehåll:** inga mejltexter, fil-innehåll, tokens eller hemligheter. Metrics är antal och
  tider, inte data. **GDPR-säkert by design.**

## Exponering
- **`/metrics`** (Prometheus) — bunden localhost / bakom auth, **aldrig publik** (som setup-UI).
  Operatören skrapar med egen Prometheus/Grafana, eller använder en minimal inbyggd statussida.
- **Loggar** till stdout (container) → operatörens loggstack (Loki/journald/valfri).
- **Single-tenant-flotta:** varje instans exponerar sina egna. Aggregering över flottan är
  enterprise (flottkonsol, ENTERPRISE.md). Lätt variant: varje instans skickar en **heartbeat** +
  `operator_alert` vid tröskelbrott.

## Larm (→ operator_alert)
Tröskelbrott skickar `operator_alert`-mejl (SYSTEM-MAIL.md): felandel över X %, backend nere,
circuit öppen, kö-mättnad, disk/kvot, cert nära utgång. Så en trasig kundinstans larmar **dig innan
kunden ringer**.

## Visa-ditt-arbete (användar-vänd transparens)
Audit ovan är *operatörs*-vänd. Användaren behöver också se **vad AI:n läste och varför** — avgörande
för tillit till en AI som agerar på känslig data.
- Svar kan åtföljas av härkomst: *"Jag läste dessa 3 mejl + denna händelse för att svara."*
- Skiljt från audit: detta är *för användaren i stunden*, inte en compliance-logg. (OPEN-GAPS #7)

## Config (`config/observability.yaml`)
```yaml
observability:
  metrics: { enabled: true, bind: "127.0.0.1:9090" }
  logs:    { format: json, level: info }
  health_endpoint: "/health"
  alerts:
    error_rate_pct: 10
    backend_down: true
    circuit_open: true
    cert_days_left: 14
    to: operator            # via system_mail operator_alert
```

## Faser
1. **Strukturerade loggar + `/health`.**
2. **`/metrics`** med kärn-metrics.
3. **Tröskellarm → operator_alert.**
4. Valfritt: OpenTelemetry-traces; flott-aggregering (enterprise).

## Acceptanskriterier
- [ ] `/health` ger snabb liveness/readiness; `/metrics` exponerar kärn-metrics, ej publikt.
- [ ] Loggar är strukturerade med korrelations-id och innehåller aldrig hemligheter/PII-innehåll.
- [ ] Tröskelbrott (backend nere, hög felandel, öppen circuit) larmar operatören via mejl.
- [ ] En operatör kan se användning, latens och felandel per verktyg/backend över tid.
