# SPDX-License-Identifier: AGPL-3.0-or-later
"""whoami — returns the calling user's identity and project grants."""

from __future__ import annotations

from pathlib import Path

from ..acl import Acl

# Minnestrappan (SELF-IMPROVING-SYSTEM.md Fas B) — reglerna följer med i varje
# whoami-svar så alla anslutna modeller (BYO eller egen) bär samma disciplin.
MEMORY_RULES = (
    "Minnestrappan: (1) Osäkra påståenden sparas som status 'hypotes' "
    "(memory_write default). (2) Befordra till 'verifierad' via "
    "memory_set_status ENDAST efter bekräftelse i källa/verktyg eller från "
    "en människa — aldrig för att det låter rimligt. (3) Vid konsultation: "
    "väg 'verifierad' över 'hypotes', och presentera aldrig en hypotes som "
    "faktum — säg att den är obekräftad."
)


def whoami(acl: Acl, user_id: str, vault: Path | None = None) -> dict:
    """Return user id and all project grants visible to this user.

    If vault is provided, also includes onboarding status.
    """
    grants = acl.grants(user_id)
    result = {
        "user_id": user_id,
        "projects": {project: {"role": role} for project, role in grants.items()},
        "memory_rules": MEMORY_RULES,
    }
    if vault is not None:
        from .onboarding import check_onboarding
        result.update(check_onboarding(user_id, vault))
    return result
