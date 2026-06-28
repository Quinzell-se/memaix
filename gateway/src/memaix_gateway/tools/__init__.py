"""Tool modules — STUBS to implement per docs/BUILD.md.

SPDX-License-Identifier: AGPL-3.0-or-later

Each module registers project-scoped MCP tools. Every tool takes a `project` argument and must
call Acl.enforce(user, project, need) before any backend access.

Planned modules:
  email.py     - IMAP/SMTP: list, read, search, create_draft, (send behind allow_send)
  calendar.py  - CalDAV:   list, find_free_time, create, update, delete
  files.py     - WebDAV:   list, read, search, write
  memory.py    - git vault: read, search, append, write, history, revert (commit per write)
  backlog.py   - markdown:  add, list, get, score, comment, set_status (set_status = owner)
  whoami.py    - returns the caller's identity and visible projects
"""
