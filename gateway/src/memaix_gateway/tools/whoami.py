# SPDX-License-Identifier: AGPL-3.0-or-later
"""whoami — returns the calling user's identity and project grants."""

from __future__ import annotations

from ..acl import Acl


def whoami(acl: Acl, user_id: str) -> dict:
    """Return user id and all project grants visible to this user."""
    grants = acl.grants(user_id)
    return {
        "user_id": user_id,
        "projects": {project: {"role": role} for project, role in grants.items()},
    }
