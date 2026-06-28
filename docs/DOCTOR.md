# Doctor — verifiering & hälsokontroll

`memaix doctor` kontrollerar att hela stacken är rätt konfigurerad och fungerar. Körs sist i
wizarden (steg 9), och fristående när som helst. **Read-only och säker i drift** — ändrar inget
(utom valfritt test-mejl som flaggas först).

## Kontroller

Varje rad är `PASS` / `WARN` / `FAIL` med en kort förklaring och en fix-pekare.

### Kärna / gateway
| Kontroll | PASS-villkor |
|---|---|
| Config parsar | brand/memaix/acl.yaml giltigt schema |
| OAuth-nyckel | `MEMAIX_OAUTH_SIGNING_KEY` satt |
| Gateway frisk | hälso-endpoint svarar |
| Publik URL nåbar | `public_url` svarar utifrån, giltig TLS |
| OAuth-metadata | `.well-known`-endpoint nåbar |
| MCP-endpoint | Streamable HTTP svarar |

### Tunnel / nätverk
| Kontroll | PASS-villkor |
|---|---|
| Tunnel uppe | cloudflared ansluten / reverse proxy nåbar |
| Bot Fight av | ingen bot-blockering på MCP-hostnamnet (annars `WARN`) |
| Ingen Access framför | `WARN` om Cloudflare Access "Managed OAuth" tycks ligga framför (bryter iOS) |

### RBAC / ACL
| Kontroll | PASS-villkor |
|---|---|
| Owner finns | minst en `owner` per projekt |
| Secrets lösta | alla `*_ref` finns i `.env` |
| oauth_sub unika | inga dubbletter |
| Isoleringstest | syntetisk användare utan grant **nekas** (dry-run enforcement) |

### Backends (per projekt)
| Kontroll | PASS-villkor |
|---|---|
| Mejl | IMAP-login + SMTP-auth funkar; `allow_send`-status rapporteras |
| Kalender | CalDAV nåbar + auth |
| Filer | WebDAV nåbar + auth |
| Google/MS | token giltig / inte `needs_relink` |
| Vault | git-repo initierat, skrivbart, rent |

### Nextcloud (om bundlad)
| Kontroll | PASS-villkor |
|---|---|
| NC frisk | `occ status` = installed |
| Projektanvändare | finns; app-lösen autentiserar mot WebDAV/CalDAV |
| Kalendrar | skapade per projekt |

### Systemmejl
| Kontroll | PASS-villkor |
|---|---|
| Provider konfigurerad | credentials giltiga (API-ping / SMTP-auth) |
| Avsändardomän | SPF/DKIM/DMARC-poster finns (DNS-uppslag); `WARN` om DMARC `p=none` |
| Test-mejl (valfritt) | skickas till operatör på begäran |

### Säkerhetsposture
| Kontroll | PASS-villkor |
|---|---|
| Setup-UI avstängt | setup-endpoints lyssnar inte i drift |
| Filrättigheter | `.env`/secrets ej världsläsbara |
| TLS-cert | inte nära utgång (annars `WARN`) |
| `allow_send` | status rapporteras (`WARN` om på) |

### Minne / innehåll
| Kontroll | PASS-villkor |
|---|---|
| Vault skrivbar | testcommit lyckas och rullas tillbaka |
| `shared/` komplett | manual/skrivstil/onboarding finns (annars `WARN`) |

## Rapportering

```
Memaix doctor — instans: notify.example.com
  Kärna .............. PASS (6/6)
  Tunnel ............. PASS (3/3)
  RBAC .............. FAIL  ← acl: projekt "project-b" saknar owner  → fix: sätt en owner i acl.yaml
  Backends .......... WARN  ← acme: allow_send=true  → bekräfta avsiktligt
  Nextcloud ......... PASS (3/3)
  Systemmejl ........ WARN  ← DMARC p=none på notify.  → skärp till quarantine
  Säkerhet .......... PASS (4/4)
  Minne ............. PASS (2/2)

Summa: 18 PASS · 2 WARN · 1 FAIL
```

- **Severitet:** `FAIL` blockerar "klart" och ger exit-kod ≠ 0. `WARN` är rådgivande (exit 0).
- **Varje rad pekar på fixen** — config-fält, kommando, eller doc-länk.
- **Lägen:** human (färgad), `--json` (automation/CI), `--quiet` (bara summa + FAIL).

## Användning
- **Efter install:** wizarden kör doctor och säger inte "klart" förrän inga `FAIL` kvarstår.
- **Fristående:** `memaix doctor` när som helst (read-only).
- **Schemalagt (valfritt):** kör periodiskt; vid `FAIL` skicka `operator_alert`-mejl (SYSTEM-MAIL.md).

## Acceptanskriterier
- [ ] Doctor är read-only och säker att köra i drift.
- [ ] Varje kontroll ger PASS/WARN/FAIL med fix-pekare.
- [ ] `FAIL` ger exit-kod ≠ 0; `WARN` ger 0.
- [ ] `--json` ger maskinläsbar output för CI/övervakning.
- [ ] Isoleringstestet bekräftar att en användare utan grant nekas.
- [ ] Wizarden blockerar slutförande tills inga `FAIL` återstår.
