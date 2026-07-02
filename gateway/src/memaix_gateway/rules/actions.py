# SPDX-License-Identifier: AGPL-3.0-or-later
"""Run a rule's action against the real tools (or an injected dispatch for
testing/dry-run). See docs/FEATURE-AUTOMATION-RULES.md §4/§5.

Outgoing actions (email_send) are NOT treated specially here — email_send's
own outbox gate (tools/email.py) already queues it for approval when the
project is in 'review' mode, so a rule can never bypass the outbox.
"""

from __future__ import annotations

from typing import Callable


def _resolve_params(params: dict, payload: dict) -> dict:
    """Map '<field>_from' entries to payload[value]; everything else is literal."""
    payload = payload or {}
    resolved: dict = {}
    for key, value in (params or {}).items():
        if key.endswith("_from"):
            resolved[key[: -len("_from")]] = payload.get(value, "")
        else:
            resolved[key] = value
    return resolved


def _default_action_dispatch() -> dict[str, Callable]:
    from ..tools import backlog as t_backlog
    from ..tools import email as t_email
    from ..tools import memory as t_memory
    from ..tools import pm as t_pm

    return {
        "backlog_add": t_backlog.backlog_add,
        "memory_append": t_memory.memory_append,
        "pm_raid_add": t_pm.pm_raid_add,
        "email_create_draft": t_email.email_create_draft,
        "email_send": t_email.email_send,
    }


def _run_notify(acl, user: str, params: dict, *, tools: dict | None) -> dict:
    channels = (tools or {}).get("_channels")
    if channels is None:
        import os
        from pathlib import Path
        from ..notify.channels import build_channels
        from ..notify.store import NotifyStore

        notify_store = (tools or {}).get("_notify_store")
        if notify_store is None:
            db_path = Path(os.environ.get("MEMAIX_NOTIFY_DB", "/tmp/memaix-notify.db"))
            notify_store = NotifyStore.for_path(db_path)
        prefs = notify_store.get_prefs(user) or {}
        channels = build_channels(prefs.get("channels", []), acl=acl)

    text = params.get("text", "")
    errors = []
    for ch in channels:
        try:
            ch.send("Memaix — automation", text, text)
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))
    return {"ok": not errors, "errors": errors, "channels_used": len(channels)}


def run_action(
    acl, user: str, action: dict, payload: dict, *, tools: dict | None = None, dry_run: bool = False,
) -> dict:
    """Execute one rule action. Never raises — failures come back as {"ok": False, "error": ...}."""
    action_type = action.get("type")
    params = _resolve_params(action.get("params", {}), payload)
    project = params.pop("project", None)

    if dry_run:
        return {"ok": True, "dry_run": True, "type": action_type, "project": project, "params": params}

    if action_type == "notify":
        return _run_notify(acl, user, params, tools=tools)

    if not project:
        return {"ok": False, "error": "action params must include 'project'"}

    dispatch = tools if tools is not None else _default_action_dispatch()
    fn = dispatch.get(action_type)
    if fn is None:
        return {"ok": False, "error": f"unknown action type: {action_type!r}"}

    try:
        result = fn(acl, user, project, **params)
        return {"ok": True, "result": result}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
