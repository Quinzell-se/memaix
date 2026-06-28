# Memaix MCP-API — verktygsreferens

Kontraktet för vad man kan göra via MCP mot en Memaix-instans. Detta är gränssnittsspecen som
gatewayen implementerar (se `BUILD.md` för bygg-ordning). PM-modulens verktyg dokumenteras i
`ADDON-PM-BUILD.md`.

## Grundläggande

- **Transport:** Streamable HTTP MCP. En connector-URL (instansens publika adress).
- **Autentisering:** OAuth 2.1 (PKCE + CIMD). Varje anrop sker som en identifierad användare.
- **`project` är obligatoriskt** i alla verktyg utom `whoami`. Det avgör vilken brevlåda,
  kalender, mapp och vault som används.
- **Rollkontroll (RBAC):** före varje anrop kontrolleras att användaren har minst den roll som
  krävs på `project`. Bobrs `access_denied`. Roller: `reader` < `collaborator` < `owner`.
- **Tider:** ISO 8601 med tidszon (`2026-06-28T14:00:00+02:00`).
- **Skrivningar i minne/backlog** returnerar en git-commit-referens (spårbarhet).

## Felmodell
| Fel | När |
|---|---|
| `access_denied` | Saknar roll/projekt-access |
| `not_found` | Okänt id/sökväg/projekt |
| `validation_error` | Saknade/felaktiga argument |
| `feature_disabled` | T.ex. `email_send` när `allow_send: false` |
| `backend_error` | Fel mot mejl/kalender/filer |

---

## Mejl  (backend: IMAP/SMTP)

| Verktyg | Parametrar | Returnerar | Roll |
|---|---|---|---|
| `email_list` | `project, folder="INBOX", limit=20` | `[{id, from, subject, date, snippet, unread}]` | collaborator |
| `email_read` | `project, id` | `{id, from, to, cc, subject, date, body, attachments:[{name,size}]}` | collaborator |
| `email_search` | `project, query, limit=20` | `[{id, from, subject, date, snippet}]` | collaborator |
| `email_create_draft` | `project, to, subject, body, cc?, in_reply_to?` | `{draft_id, folder:"Drafts"}` | collaborator |
| `email_send` | `project, to, subject, body, cc?` | `{sent:true}` | **owner** + `allow_send` |

> Standard: AI:n skapar utkast. `email_send` är avstängt tills `allow_send: true` i config.

## Kalender  (backend: CalDAV)

| Verktyg | Parametrar | Returnerar | Roll |
|---|---|---|---|
| `calendar_list` | `project, start, end` | `[{id, title, start, end, location, attendees}]` | collaborator |
| `calendar_find_free` | `project, duration_min, within_start, within_end` | `[{start, end}]` | collaborator |
| `calendar_create` | `project, title, start, end, attendees?, location?, description?` | `{id}` | collaborator |
| `calendar_update` | `project, id, {title?, start?, end?, ...}` | `{id}` | collaborator |
| `calendar_delete` | `project, id` | `{deleted:true}` | collaborator |

## Filer  (backend: WebDAV)

| Verktyg | Parametrar | Returnerar | Roll |
|---|---|---|---|
| `files_list` | `project, path="/"` | `[{path, name, type, size, modified}]` | collaborator |
| `files_read` | `project, path` | `{path, content, mime}` | collaborator |
| `files_search` | `project, query` | `[path]` | collaborator |
| `files_write` | `project, path, content` | `{path, bytes}` | collaborator |

## Minne  (backend: git-versionerad markdown)

| Verktyg | Parametrar | Returnerar | Roll |
|---|---|---|---|
| `memory_read` | `project, note` | `{path, content}` | reader |
| `memory_search` | `project, query` | `[{path, snippet}]` | reader |
| `memory_append` | `project, note, text` | `{path, commit}` | collaborator |
| `memory_write` | `project, note, content` | `{path, commit}` | collaborator |
| `memory_history` | `project, note?, limit=20` | `[{commit, author, date, message}]` | reader |
| `memory_revert` | `project, commit` | `{reverted_to, new_commit}` | collaborator |

> Varje skrivning committas automatiskt. `note` är en sökväg i projektets vault, t.ex.
> `decisions.md` eller `about-bob.md`.

## Backlog  (markdown med frontmatter i vaulten)

| Verktyg | Parametrar | Returnerar | Roll |
|---|---|---|---|
| `backlog_add` | `project, title, description, category?, author?` | `{id, status:"inbox"}` | collaborator |
| `backlog_list` | `project, status?, category?` | `[{id, title, status, category, value, complexity, risk}]` | reader |
| `backlog_get` | `project, id` | fullt item (frontmatter + text) | reader |
| `backlog_score` | `project, id, value?, complexity?, risk?` | uppdaterat item | collaborator |
| `backlog_comment` | `project, id, text` | `{ok, commit}` | collaborator |
| `backlog_set_status` | `project, id, status` | uppdaterat item | **owner** |

> Statusflöde: `inbox → triaged → evaluated → approved/rejected → in-dev → done`.
> Poäng 1–5: `value` (nytta), `complexity` (komplexitet), `risk` (säkerhet/risk).

## Övrigt

| Verktyg | Parametrar | Returnerar | Roll |
|---|---|---|---|
| `whoami` | — | `{user, projects:[{project, role}]}` | alla |

## PM-modulen (tillägg)
`pm_*`-verktyg (sprintplanering, WBS, milstolpar, schemaläggning, RAID, statusrapport) specas i
`ADDON-PM-BUILD.md`. De följer samma konventioner: `project` obligatoriskt, RBAC, artefakter som
git-committad markdown.

## Versionering
Detta är v1 av gränssnittet. Tillägg av verktyg/fält är bakåtkompatibelt; ändrad semantik på
befintliga verktyg höjer major-version och dokumenteras här.
