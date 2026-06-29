# Arkitektur

```
  Användare (Claude / ChatGPT / Mistral / Perplexity — desktop & mobil)
        │  HTTPS (Streamable HTTP MCP) + OAuth 2.1/PKCE
        ▼
  Tunnel / reverse proxy  ──  mcp.kundens-domän.se
        │  (Cloudflare tunnel rekommenderas: outbound, auto-TLS, ingen portöppning)
        ▼
  Memaix gateway
        ├── AuthN: OAuth 2.1 via beprövad AS (ory Hydra; DCR+PKCE) — gateway validerar tokens
        ├── AuthZ: acl.yaml → vem får vilka projekt (RBAC)
        │
        ├── email_*     → IMAP/SMTP        [per projekt]
        ├── calendar_*  → CalDAV           [per projekt]
        ├── files_*     → WebDAV           [per projekt]
        ├── memory_*    → SQLite (aktivt) + git (historik) [per projekt]
        └── backlog_*   → markdown i vault [per projekt]
```

## Bärande val

- **En instans per deployment (single-tenant).** Varje kund kör sin egen Memaix med egen domän,
  egna tunnlar, egen branding och egen data. Enklare isolering, inget delat dataplan.
- **En connector, RBAC bakom.** Alla användare lägger in samma URL. `acl.yaml` avgör vad var och
  en ser. Externa låses till exakt ett projekt.
- **Öppna standarder i backenden.** IMAP/SMTP, CalDAV, WebDAV, git — inga proprietära beroenden.
- **Auth via beprövad komponent.** OAuth2 hanteras av ory Hydra (certifierad, DCR), inte hemsnickrad
  kod. Tunneln är ren proxy (ingen Access). Se `REVIEW-RESPONSE.md`.
- **Minne = SQLite + git.** Aktivt tillstånd i SQLite (snabbt, transaktioner, concurrency); git tar
  versionshistorik **asynkront** (rollback). Inte commit-per-skrivning i het väg. Se `SAFETY.md`.
- **AI-agnostiskt.** MCP är öppen standard → Claude, ChatGPT, Mistral, Perplexity m.fl.

## Verktyg (alla projekt-scopade, valideras mot acl.yaml)

| Grupp | Verktyg |
|---|---|
| Mejl | `email_list/read/search/create_draft` (+ `email_send` bakom `allow_send`) |
| Kalender | `calendar_list/find_free_time/create/update/delete` |
| Filer | `files_list/read/search/write` |
| Minne | `memory_read/search/append/write/history/revert` |
| Backlog | `backlog_add/list/get/score/comment/set_status` (set_status = owner) |
| Events | utgående **webhooks** vid ändring · inkommande (signerade) endpoints (formulär → backlog) |
| Övrigt | `whoami` |

> **Webhooks/events** (OPEN-GAPS #17): integration åt båda håll — Memaix notifierar andra system, och
> externa händelser kan skapa items. Signerade och projekt-scopade.
