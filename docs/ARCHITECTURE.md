# Arkitektur

```
  Användare (Claude / ChatGPT / Mistral / Perplexity — desktop & mobil)
        │  HTTPS (Streamable HTTP MCP) + OAuth 2.1/PKCE
        ▼
  Tunnel / reverse proxy  ──  mcp.kundens-domän.se
        │  (Cloudflare tunnel rekommenderas: outbound, auto-TLS, ingen portöppning)
        ▼
  Memaix gateway
        ├── AuthN: egen OAuth 2.1-server (CIMD + PKCE)
        ├── AuthZ: acl.yaml → vem får vilka projekt (RBAC)
        │
        ├── email_*     → IMAP/SMTP        [per projekt]
        ├── calendar_*  → CalDAV           [per projekt]
        ├── files_*     → WebDAV           [per projekt]
        ├── memory_*    → git-vaults       [per projekt]
        └── backlog_*   → markdown i vault [per projekt]
```

## Bärande val

- **En instans per deployment (single-tenant).** Varje kund kör sin egen Memaix med egen domän,
  egna tunnlar, egen branding och egen data. Enklare isolering, inget delat dataplan.
- **En connector, RBAC bakom.** Alla användare lägger in samma URL. `acl.yaml` avgör vad var och
  en ser. Externa låses till exakt ett projekt.
- **Öppna standarder i backenden.** IMAP/SMTP, CalDAV, WebDAV, git — inga proprietära beroenden.
- **Minne = git.** Varje projekt-vault är ett git-repo. Skrivningar committas → historik + rollback.
- **AI-agnostiskt.** MCP är öppen standard → Claude, ChatGPT, Mistral, Perplexity m.fl.

## Verktyg (alla projekt-scopade, valideras mot acl.yaml)

| Grupp | Verktyg |
|---|---|
| Mejl | `email_list/read/search/create_draft` (+ `email_send` bakom `allow_send`) |
| Kalender | `calendar_list/find_free_time/create/update/delete` |
| Filer | `files_list/read/search/write` |
| Minne | `memory_read/search/append/write/history/revert` |
| Backlog | `backlog_add/list/get/score/comment/set_status` (set_status = owner) |
| Övrigt | `whoami` |
