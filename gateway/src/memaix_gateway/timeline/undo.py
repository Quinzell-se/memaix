# SPDX-License-Identifier: AGPL-3.0-or-later
"""Undo — invert a recorded reversible action."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

# The role required to undo an action is the role its *original* tool call
# required — an undo must never be easier to trigger than the action itself.
_NEED_FOR_TOOL: dict[str, str] = {
    "memory_write": "collaborator",
    "memory_append": "collaborator",
    "calendar_create": "collaborator",
    "backlog_add": "collaborator",
    "board_move": "owner",  # matches board/routes.py:api_item_patch's acl.enforce
}


def _board_move_undo(acl, user_id: str, project: str, *, item_id: str, status: str) -> dict:
    """Adapter so board_move's inverse fits the (acl, user, project, **args)
    dispatch convention — board.store.write_status() itself has no acl/user
    parameters (the board route enforces access before calling it)."""
    from ..board import store as board_store

    vault = acl.resource(project, "vault")
    if not vault:
        raise ValueError(f"project {project!r} has no vault configured")
    return board_store.write_status(Path(vault), item_id, status)


def _default_dispatch() -> dict[str, Callable]:
    # Imported lazily — tools.memory/tools.calendar/tools.backlog don't import
    # timeline.undo, so this isn't strictly required for cycle-safety, but it
    # matches the pattern used by outbox.execute and keeps import cost lazy.
    from ..tools import backlog as t_backlog
    from ..tools import calendar as t_calendar
    from ..tools import memory as t_memory

    return {
        "memory_revert": t_memory.memory_revert,
        "calendar_delete": t_calendar.calendar_delete,
        "backlog_set_status": t_backlog.backlog_set_status,
        "board_move": _board_move_undo,
    }


def undo(store, acl, user: str, action_id: str, *, tools: dict[str, Callable] | None = None) -> dict:
    """Invert a recorded action. Returns a result dict; never raises for
    expected failure modes (missing/irreversible/conflict) — only AccessDenied
    propagates, since that's a caller-programming-error signal like elsewhere
    in the gateway."""
    action = store.get(action_id)
    if action is None:
        raise FileNotFoundError(f"no such action: {action_id!r}")

    if not action["reversible"]:
        return {"ok": False, "error": "irreversible", "action_id": action_id}
    if action["status"] != "done":
        return {
            "ok": False,
            "error": f"cannot undo an action with status {action['status']!r}",
            "action_id": action_id,
        }

    need = _NEED_FOR_TOOL.get(action["tool"], "owner")
    acl.enforce(user, action["project"], need)  # raises AccessDenied

    claimed = store.claim_undo(action_id)
    if claimed is None:
        return {"conflict": True, "action_id": action_id}

    inverse = claimed["inverse"]
    dispatch = tools if tools is not None else _default_dispatch()
    fn = dispatch.get(inverse["tool"])
    if fn is None:
        store.mark_undo_failed(action_id)
        return {"ok": False, "error": f"no undo executor for {inverse['tool']!r}", "action_id": action_id}

    try:
        result = fn(acl, user, action["project"], **inverse["args"])
    except Exception as exc:  # noqa: BLE001 - surfaced as a result dict
        store.mark_undo_failed(action_id)
        return {"ok": False, "error": str(exc), "action_id": action_id}

    if isinstance(result, dict) and result.get("conflict"):
        store.mark_undo_failed(action_id)
        return {
            "ok": False,
            "error": "conflict: the item changed since this action — refusing to overwrite",
            "action_id": action_id,
            "detail": result,
        }

    undo_action_id = store.record(
        user, action["project"], inverse["tool"], f"Ångrade: {action['summary']}",
        None, undo_of=action_id,
    )
    store.link_undo(action_id, undo_action_id)

    return {"ok": True, "action_id": action_id, "undo_action_id": undo_action_id, "result": result}
