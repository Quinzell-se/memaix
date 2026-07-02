# SPDX-License-Identifier: AGPL-3.0-or-later
"""backlog_* tools — YAML-frontmatter markdown items in {vault}/backlog/.

Item lifecycle:
  inbox → triaged → evaluated → approved / rejected
  approved → in-dev → done

Optimistic locking: every mutating call takes expected_version (int).
If the file's version != expected_version the call returns
  {"conflict": True, "current_version": N}
and makes no changes.

ID format: uuid4().hex[:8]  (8 lowercase hex chars, e.g. "a1b2c3d4")
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .. import frontmatter as fm
from ..acl import Acl
from ..paths import validate_id

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

VALID_STATUSES: frozenset[str] = frozenset(
    {"inbox", "triaged", "evaluated", "approved", "rejected", "in-dev", "done"}
)

# ------------------------------------------------------------------
# Per-vault write locks (module-level, keyed by resolved vault path)
# ------------------------------------------------------------------

_vault_locks: dict[str, threading.Lock] = {}
_meta_lock = threading.Lock()


def _get_lock(vault_str: str) -> threading.Lock:
    with _meta_lock:
        if vault_str not in _vault_locks:
            _vault_locks[vault_str] = threading.Lock()
        return _vault_locks[vault_str]


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _backlog_dir(acl: Acl, project: str) -> Path:
    vault_str = acl.resource(project, "vault")
    if not vault_str:
        raise ValueError(f"project {project!r} has no vault configured")
    d = Path(vault_str) / "backlog"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _parse_item(path: Path) -> dict:
    """Read and parse a backlog markdown file.  Returns merged dict (meta + description)."""
    text = path.read_text()
    meta, body = fm.split(text)
    if not meta:
        raise ValueError(f"missing or malformed frontmatter in {path.name}")
    meta["description"] = body
    return meta


def _write_item(path: Path, meta: dict) -> None:
    """Serialise a backlog item back to markdown with YAML frontmatter (atomic)."""
    # Pop description before serialising frontmatter
    description = meta.pop("description", "")
    fm.write_atomic(path, fm.join(meta, description))
    meta["description"] = description  # restore in-place


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


def backlog_add(
    acl: Acl,
    user_id: str,
    project: str,
    title: str,
    description: str,
    category: str | None = None,
) -> dict:
    """Create a new backlog item.  Returns {id, status}."""
    acl.enforce(user_id, project, "collaborator")
    bl_dir = _backlog_dir(acl, project)
    vault_str = str(bl_dir.parent.resolve())
    lock = _get_lock(vault_str)

    item_id = uuid.uuid4().hex[:8]
    now = _now_iso()
    meta: dict = {
        "id": item_id,
        "title": title,
        "author": user_id,
        "category": category,
        "status": "inbox",
        "value": None,
        "complexity": None,
        "risk": None,
        "version": 1,
        "created_at": now,
        "updated_at": now,
        "description": description,
    }
    path = bl_dir / f"{item_id}.md"
    with lock:
        _write_item(path, meta)
    return {"id": item_id, "status": "inbox"}


def backlog_list(
    acl: Acl,
    user_id: str,
    project: str,
    status: str | None = None,
    category: str | None = None,
) -> list[dict]:
    """List backlog items, optionally filtered.  Returns list of item dicts."""
    acl.enforce(user_id, project, "reader")
    bl_dir = _backlog_dir(acl, project)
    items: list[dict] = []
    for p in sorted(bl_dir.glob("*.md")):
        try:
            item = _parse_item(p)
        except (ValueError, yaml.YAMLError):
            continue
        if status and item.get("status") != status:
            continue
        if category and item.get("category") != category:
            continue
        items.append(item)
    return items


def backlog_get(acl: Acl, user_id: str, project: str, id: str) -> dict:
    """Fetch a single backlog item.  Raises FileNotFoundError if absent."""
    acl.enforce(user_id, project, "reader")
    validate_id(id, kind="backlog id")
    bl_dir = _backlog_dir(acl, project)
    path = bl_dir / f"{id}.md"
    if not path.exists():
        raise FileNotFoundError(f"backlog item not found: {id!r}")
    return _parse_item(path)


def backlog_score(
    acl: Acl,
    user_id: str,
    project: str,
    id: str,
    expected_version: int,
    value: int | None = None,
    complexity: int | None = None,
    risk: int | None = None,
) -> dict:
    """Update scoring fields.  Returns {id, version, commit} or conflict dict."""
    acl.enforce(user_id, project, "collaborator")
    validate_id(id, kind="backlog id")
    bl_dir = _backlog_dir(acl, project)
    lock = _get_lock(str(bl_dir.parent.resolve()))
    path = bl_dir / f"{id}.md"
    with lock:
        if not path.exists():
            raise FileNotFoundError(f"backlog item not found: {id!r}")
        item = _parse_item(path)
        if item.get("version") != expected_version:
            return {"conflict": True, "current_version": item.get("version")}
        if value is not None:
            item["value"] = value
        if complexity is not None:
            item["complexity"] = complexity
        if risk is not None:
            item["risk"] = risk
        item["version"] = expected_version + 1
        item["updated_at"] = _now_iso()
        _write_item(path, item)
    return {"id": id, "version": item["version"], "commit": "local"}


def backlog_comment(
    acl: Acl,
    user_id: str,
    project: str,
    id: str,
    text: str,
    expected_version: int,
) -> dict:
    """Append a comment to an item's body.  Returns {ok, commit} or conflict dict."""
    acl.enforce(user_id, project, "collaborator")
    validate_id(id, kind="backlog id")
    bl_dir = _backlog_dir(acl, project)
    lock = _get_lock(str(bl_dir.parent.resolve()))
    path = bl_dir / f"{id}.md"
    with lock:
        if not path.exists():
            raise FileNotFoundError(f"backlog item not found: {id!r}")
        item = _parse_item(path)
        if item.get("version") != expected_version:
            return {"conflict": True, "current_version": item.get("version")}
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        item["description"] = (
            (item.get("description") or "") + f"\n\n---\n**{user_id}** ({ts}):\n{text}"
        )
        item["version"] = expected_version + 1
        item["updated_at"] = _now_iso()
        _write_item(path, item)
    return {"ok": True, "commit": "local"}


def backlog_set_status(
    acl: Acl,
    user_id: str,
    project: str,
    id: str,
    status: str,
    expected_version: int,
) -> dict:
    """Transition status.  Requires owner.  Returns {id, status, commit} or conflict dict."""
    acl.enforce(user_id, project, "owner")
    validate_id(id, kind="backlog id")
    if status not in VALID_STATUSES:
        raise ValueError(
            f"invalid status {status!r}; valid values: {sorted(VALID_STATUSES)}"
        )
    bl_dir = _backlog_dir(acl, project)
    lock = _get_lock(str(bl_dir.parent.resolve()))
    path = bl_dir / f"{id}.md"
    with lock:
        if not path.exists():
            raise FileNotFoundError(f"backlog item not found: {id!r}")
        item = _parse_item(path)
        if item.get("version") != expected_version:
            return {"conflict": True, "current_version": item.get("version")}
        item["status"] = status
        item["version"] = expected_version + 1
        item["updated_at"] = _now_iso()
        _write_item(path, item)
    return {"id": id, "status": status, "commit": "local"}
