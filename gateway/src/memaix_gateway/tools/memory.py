# SPDX-License-Identifier: AGPL-3.0-or-later
"""memory_* tools — structured note store backed by MemoryStore.

All functions are pure (acl + user_id injected, no global state).
ACL is enforced before any backend call (SAFETY.md §2).

Path rules for notes:
  - Must be relative (no leading /)
  - Must not contain '..' components
  - e.g. "ideas/feature-x.md", "standup/2024-06-29.md"
"""

from __future__ import annotations

from pathlib import Path

from ..acl import Acl
from ..backends.memory_store import MemoryStore
from ..paths import validate_relative_path

# ------------------------------------------------------------------
# Validation
# ------------------------------------------------------------------


def _validate_note_path(note: str) -> None:
    validate_relative_path(note, kind="note path")


def _get_store(acl: Acl, project: str) -> MemoryStore:
    vault_str = acl.resource(project, "vault")
    if not vault_str:
        raise ValueError(f"project {project!r} has no vault configured")
    return MemoryStore.for_vault(Path(vault_str))


# ------------------------------------------------------------------
# Read tools — require "reader"
# ------------------------------------------------------------------


def memory_read(acl: Acl, user_id: str, project: str, note: str) -> dict:
    """Return {path, content} for a note.  Raises FileNotFoundError if absent."""
    acl.enforce(user_id, project, "reader")
    _validate_note_path(note)
    store = _get_store(acl, project)
    content = store.read(note)
    if content is None:
        raise FileNotFoundError(f"note not found: {note!r}")
    return {"path": note, "content": content}


def memory_search(acl: Acl, user_id: str, project: str, query: str) -> list[dict]:
    """FTS5 search.  Returns [{path, snippet}]."""
    acl.enforce(user_id, project, "reader")
    store = _get_store(acl, project)
    return store.search(query)


def memory_history(
    acl: Acl,
    user_id: str,
    project: str,
    note: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Git log for a note or the whole vault.  Returns [{hash, author, date, message}]."""
    acl.enforce(user_id, project, "reader")
    store = _get_store(acl, project)
    return store.history(note, limit)


# ------------------------------------------------------------------
# Write tools — require "collaborator"
# ------------------------------------------------------------------


def memory_write(
    acl: Acl, user_id: str, project: str, note: str, content: str
) -> dict:
    """Overwrite note.  Returns {path, commit}."""
    acl.enforce(user_id, project, "collaborator")
    _validate_note_path(note)
    store = _get_store(acl, project)
    commit = store.write(note, content, user_id)
    return {"path": note, "commit": commit}


def memory_append(
    acl: Acl, user_id: str, project: str, note: str, text: str
) -> dict:
    """Append text to note (creates if absent).  Returns {path, commit}."""
    acl.enforce(user_id, project, "collaborator")
    _validate_note_path(note)
    store = _get_store(acl, project)
    commit = store.append(note, text, user_id)
    return {"path": note, "commit": commit}


def memory_revert(
    acl: Acl, user_id: str, project: str, commit: str
) -> dict:
    """Revert a git commit.  Returns {reverted_to, new_commit}."""
    acl.enforce(user_id, project, "collaborator")
    store = _get_store(acl, project)
    new_commit = store.revert(commit)
    return {"reverted_to": commit, "new_commit": new_commit}
