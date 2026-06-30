# SPDX-License-Identifier: AGPL-3.0-or-later
"""Onboarding helpers — check whether a user has a completed profile and scaffold one."""

from __future__ import annotations

from pathlib import Path

DEFAULT_INTERVIEW = """# Onboarding-intervju
Hej! Jag behöver lära känna dig för att hjälpa dig bättre.
1. Vad heter du och vad är din roll?
2. Vilka projekt jobbar du med?
3. Vad är ditt primära ansvar?
4. Hur föredrar du att kommunicera och jobba?
"""


def _interview_template(vault: Path) -> str:
    custom = vault / "shared" / "onboarding-interview.md"
    if custom.exists():
        return custom.read_text()
    return DEFAULT_INTERVIEW


def check_onboarding(user_id: str, vault: Path) -> dict:
    """Return onboarding status for user_id.

    Returns a dict with keys:
      - needs_onboarding: bool
      - profile_status: 'missing' | 'incomplete' | 'complete'
      - interview_template: str | None  (present when needs_onboarding is True)
    """
    profile_path = vault / "shared" / f"om-{user_id}.md"

    if not profile_path.exists():
        return {
            "needs_onboarding": True,
            "profile_status": "missing",
            "interview_template": _interview_template(vault),
        }

    content = profile_path.read_text()
    if "profil_status: ofullständig" in content:
        return {
            "needs_onboarding": True,
            "profile_status": "incomplete",
            "interview_template": _interview_template(vault),
        }

    return {
        "needs_onboarding": False,
        "profile_status": "complete",
    }


def complete_onboarding(user_id: str, vault: Path, profile_content: str) -> dict:
    """Write om-{user_id}.md with profil_status: klar. Returns {'ok': True}."""
    shared = vault / "shared"
    shared.mkdir(parents=True, exist_ok=True)

    # Prepend frontmatter only if there isn't any already.
    if not profile_content.lstrip().startswith("---"):
        profile_content = f"---\nprofil_status: klar\n---\n{profile_content}"

    profile_path = shared / f"om-{user_id}.md"
    profile_path.write_text(profile_content)
    return {"ok": True}
