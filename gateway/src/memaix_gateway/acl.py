"""Access control — the core that makes one connector safe for many people.

SPDX-License-Identifier: AGPL-3.0-or-later

Every tool call passes through `enforce(user, project, need)` before touching a backend.
This module is the security boundary; keep it simple and well-tested.
"""

from __future__ import annotations

# Role hierarchy: higher index = more privilege.
ROLES = ("reader", "collaborator", "owner")


class AccessDenied(Exception):
    """Raised when a user lacks the required role on a project."""


def _rank(role: str) -> int:
    try:
        return ROLES.index(role)
    except ValueError:
        return -1


class Acl:
    """Loaded from config/acl.yaml. See config/acl.example.yaml for shape."""

    def __init__(self, users: dict, projects: dict):
        self.users = users
        self.projects = projects

    @classmethod
    def from_config(cls, cfg: dict) -> "Acl":
        return cls(users=cfg.get("users", {}), projects=cfg.get("projects", {}))

    def user_by_subject(self, oauth_sub: str) -> str | None:
        """Map an authenticated OAuth subject to an internal user id."""
        for uid, u in self.users.items():
            if u.get("oauth_sub") == oauth_sub:
                return uid
            if oauth_sub in u.get("oauth_subjects", []):
                return uid
        return None

    def grants(self, user_id: str) -> dict:
        return self.users.get(user_id, {}).get("grants", {})

    def is_admin(self, user_id: str) -> bool:
        """Return True if the user has the global admin flag set in acl.yaml.

        Strict identity check, deliberately not truthiness. ``bool()`` grants
        admin on any non-empty value: ``admin: "false"``, ``admin: "no"`` and
        ``admin: 0.1`` all coerce to True. Quoting a YAML boolean is an easy
        slip, and admin is an implicit owner on *every* project (see enforce),
        so a typo here must not widen access.

        Contrast is_disabled below: identical shape, opposite risk direction.
        This one grants, so it fails closed on anything but a real ``True``.
        """
        return self.users.get(user_id, {}).get("admin", False) is True

    def is_disabled(self, user_id: str) -> bool:
        """Return True if the user is disabled (kill-switch, users.<id>.disabled).

        Truthiness is correct here, and is not an oversight. This check *denies*
        access, so a malformed value should still lock the user out:
        ``disabled: "true"``, ``disabled: "yes"`` and ``disabled: 1`` all mean
        the operator wanted this account off. Tightening this to ``is True``
        would silently re-enable an account someone believed was disabled.

        The rule across both methods: granting checks fail closed, denying
        checks fail open. Same code, opposite direction, on purpose.
        """
        return bool(self.users.get(user_id, {}).get("disabled", False))

    def enforce(self, user_id: str, project: str, need: str = "reader") -> None:
        """Raise AccessDenied unless `user_id` has at least `need` on `project`."""
        # Kill-switch: a disabled user is denied everything, admin included. This
        # is the boundary the admin UI's per-user disable toggle relies on; the
        # lockout-prevention guard (can't disable yourself / the last admin) lives
        # in the write path, not here — enforce must fail closed regardless.
        if self.is_disabled(user_id):
            raise AccessDenied(f"{user_id} is disabled")
        # Unknown project is an error for everyone, including admin — an admin
        # acting on a typo'd/nonexistent project should get a clear failure, not
        # a silent pass that masks the mistake.
        if project not in self.projects:
            raise AccessDenied(f"unknown project: {project}")
        if self.is_admin(user_id):
            return  # admin has implicit owner on every (existing) project
        role = self.grants(user_id).get(project)
        if role is None:
            raise AccessDenied(f"{user_id} has no access to {project}")
        if _rank(role) < _rank(need):
            raise AccessDenied(f"{user_id} needs {need} on {project} (has {role})")

    def resource(self, project: str, key: str):
        """Look up a project resource (mailbox/calendar/files/vault). Returns None if absent."""
        return self.projects.get(project, {}).get(key)

    def visible_projects(self, user_id: str) -> list[str]:
        if self.is_admin(user_id):
            return sorted(self.projects.keys())
        return sorted(self.grants(user_id).keys())
