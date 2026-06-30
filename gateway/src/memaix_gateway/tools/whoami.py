# SPDX-License-Identifier: AGPL-3.0-or-later
"""whoami — returns the calling user's identity and project grants."""

from __future__ import annotations

from pathlib import Path

from ..acl import Acl


def whoami(acl: Acl, user_id: str, vault: Path | None = None) -> dict:
    """Return user id and all project grants visible to this user.

    If vault is provided, also includes onboarding status.
    """
    grants = acl.grants(user_id)
    result = {
        "user_id": user_id,
        "projects": {project: {"role": role} for project, role in grants.items()},
    }
    if vault is not None:
        from .onboarding import check_onboarding
        result.update(check_onboarding(user_id, vault))
    return result
