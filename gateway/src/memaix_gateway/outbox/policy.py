# SPDX-License-Identifier: AGPL-3.0-or-later
"""Decide whether an outgoing action executes immediately or needs approval.

See docs/FEATURE-APPROVAL-OUTBOX.md §5. Most restrictive source wins: an
unlisted recipient forces 'review' even when the project's mode is 'auto'.
"""

from __future__ import annotations


def _recipients(tool: str, args: dict) -> list[str]:
    """Extract the addresses/handles an outgoing action would reach."""
    if tool == "email_send":
        out: list[str] = []
        for field in ("to", "cc"):
            value = args.get(field)
            if value:
                out.extend(a.strip() for a in value.split(",") if a.strip())
        return out
    if tool in ("calendar_create", "calendar_update"):
        return list(args.get("attendees") or [])
    return []


def _allowlisted(recipient: str, allowlist: list[str]) -> bool:
    """Exact address match, or '@domain.example' suffix match."""
    r = recipient.strip().lower()
    for entry in allowlist:
        e = (entry or "").strip().lower()
        if not e:
            continue
        if e.startswith("@"):
            if r.endswith(e):
                return True
        elif r == e:
            return True
    return False


def action_mode(cfg: dict | None, acl, project: str, tool: str, args: dict) -> str:
    """Return 'auto' or 'review' for this action on this project.

    project's acl.resource(project, 'outbox') wins over the global
    memaix.outbox.default_mode (which defaults to 'auto' — unset config is a
    no-op, matching pre-outbox behaviour). An 'allowlist' resource, if
    present, forces 'review' for any recipient not on it, regardless of mode.
    """
    project_mode = acl.resource(project, "outbox")
    default_mode = ((cfg or {}).get("memaix", {}) or {}).get("outbox", {}).get(
        "default_mode", "auto"
    )
    mode = project_mode if project_mode in ("auto", "review") else default_mode

    allowlist = acl.resource(project, "allowlist")
    if allowlist:
        for recipient in _recipients(tool, args):
            if not _allowlisted(recipient, allowlist):
                return "review"

    return mode
