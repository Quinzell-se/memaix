# SPDX-License-Identifier: AGPL-3.0-or-later
"""Onboarding helpers — check whether a user has a completed profile and scaffold one."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_QUESTIONS = [
    "Vad heter du och vad är din roll?",
    "Vilka projekt jobbar du med, och vad är ditt primära ansvar?",
    "Vad är dina styrkor ur ett projektperspektiv?",
    "Var vill du att assistenten tar arbete av dig?",
    "Hur vill du jobba — tempo, beslutsstil, när ska jag avbryta vs jobba självständigt?",
    "Preferenser och ogillanden kring text, ton och format?",
    "Vad är dina mål just nu?",
]

DEFAULT_INTERVIEW = (
    "# Onboarding-intervju\n"
    "Hej! Jag behöver lära känna dig för att hjälpa dig bättre.\n"
    + "\n".join(f"{i+1}. {q}" for i, q in enumerate(DEFAULT_QUESTIONS))
)

_FLAG_PATH = "_system/onboarding.json"
_INCOMPLETE_TOKEN = "profil_status: ofullständig"


def _interview_template(vault: Path, cfg: dict | None = None) -> str:
    custom = vault / "shared" / "onboarding-interview.md"
    if custom.exists():
        return custom.read_text()
    questions = (cfg or {}).get("memaix", {}).get("onboarding", {}).get("questions")
    if questions:
        intro = (cfg or {}).get("memaix", {}).get("onboarding", {}).get(
            "intro", "Hej! Jag behöver lära känna dig för att hjälpa dig bättre."
        )
        return "# Onboarding-intervju\n" + intro + "\n" + "\n".join(
            f"{i+1}. {q}" for i, q in enumerate(questions)
        )
    return DEFAULT_INTERVIEW


def build_interview_prompt(user_id: str, vault: Path | None, cfg: dict | None = None) -> str:
    """Return the full prompt text for the onboarding_interview MCP prompt."""
    template = _interview_template(vault, cfg) if vault else DEFAULT_INTERVIEW
    outro = (cfg or {}).get("memaix", {}).get("onboarding", {}).get(
        "outro", "Tack! Sammanställ nu en kondenserad profil (löptext + punkter, inte råa svar) och anropa verktyget `onboarding_complete` med texten som `profile_content`. Hoppa inte över det steget — det är det som markerar onboarding som klar."
    )
    return (
        f"{template}\n\n"
        f"Fråga en fråga i taget. När alla är besvarade:\n{outro}"
    )


def check_onboarding(user_id: str, vault: Path, cfg: dict | None = None) -> dict:
    """Return onboarding status for user_id.

    Returns a dict with keys:
      - needs_onboarding: bool
      - profile_status: 'missing' | 'incomplete' | 'complete'
      - interview_template: str | None  (present when needs_onboarding is True)
      - onboarding_action: str | None   (present when needs_onboarding is True)
    """
    if (cfg or {}).get("memaix", {}).get("onboarding", {}).get("enabled") is False:
        return {"needs_onboarding": False, "profile_status": "complete"}

    # Fast path: authoritative JSON flag.
    flag_path = vault / _FLAG_PATH
    if flag_path.exists():
        try:
            flag = json.loads(flag_path.read_text())
            if flag.get("onboarded") is True:
                # Let explicit markdown re-trigger override the flag.
                profile_path = vault / "shared" / f"om-{user_id}.md"
                if profile_path.exists() and _INCOMPLETE_TOKEN in profile_path.read_text():
                    pass  # fall through to markdown check below
                else:
                    return {"needs_onboarding": False, "profile_status": "complete"}
        except (json.JSONDecodeError, OSError):
            pass

    profile_path = vault / "shared" / f"om-{user_id}.md"
    if not profile_path.exists():
        return {
            "needs_onboarding": True,
            "profile_status": "missing",
            "interview_template": _interview_template(vault, cfg),
            "onboarding_action": (
                "Den här användaren har ingen profil ännu. Erbjud en kort onboarding-intervju "
                "innan annat arbete påbörjas. Använd MCP-prompten 'onboarding_interview', eller "
                "kör frågorna i 'interview_template' en i taget, och anropa sedan verktyget "
                "'onboarding_complete' med den sammanställda profilen."
            ),
        }

    content = profile_path.read_text()
    if _INCOMPLETE_TOKEN in content:
        return {
            "needs_onboarding": True,
            "profile_status": "incomplete",
            "interview_template": _interview_template(vault, cfg),
            "onboarding_action": (
                "Onboarding-intervjun påbörjades men avbröts. Fortsätt från där ni slutade "
                "och anropa 'onboarding_complete' när profilen är klar."
            ),
        }

    return {"needs_onboarding": False, "profile_status": "complete"}


def _git_commit(vault: Path, message: str) -> None:
    if not (vault / ".git").exists():
        return
    subprocess.run(["git", "-C", str(vault), "add", "-A"], capture_output=True)
    subprocess.run(
        ["git", "-C", str(vault), "commit", "-m", message],
        capture_output=True,
    )


def complete_onboarding(user_id: str, vault: Path, profile_content: str) -> dict:
    """Write profile + completion flag and git-commit both. Returns {'ok': True}."""
    shared = vault / "shared"
    shared.mkdir(parents=True, exist_ok=True)

    if not profile_content.lstrip().startswith("---"):
        today = datetime.now(timezone.utc).date().isoformat()
        profile_content = f"---\nprofil_status: klar\nuppdaterad: {today}\n---\n{profile_content}"
    else:
        # Replace ofullständig → klar if present.
        profile_content = profile_content.replace(_INCOMPLETE_TOKEN, "profil_status: klar")

    profile_path = shared / f"om-{user_id}.md"
    profile_path.write_text(profile_content)

    # Write the authoritative flag last (crash-safe ordering).
    system_dir = vault / "_system"
    system_dir.mkdir(parents=True, exist_ok=True)
    flag = {
        "schema": 1,
        "user_id": user_id,
        "onboarded": True,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "interview_version": 1,
    }
    (system_dir / "onboarding.json").write_text(json.dumps(flag, indent=2))

    _git_commit(vault, f"onboarding: profile for {user_id}")

    return {"ok": True, "profile": f"shared/om-{user_id}.md"}
