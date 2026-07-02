# SPDX-License-Identifier: AGPL-3.0-or-later
"""Capability protocols for the connector framework (FEATURE-CONNECTOR-FRAMEWORK.md §4).

MailBackend and CalendarBackend intentionally mirror the *_imap*/*_dav* duck
types tools/email.py and tools/calendar.py already accept today (see their
module docstrings) — the point of the registry is to build one of these
objects from project config, not to redesign what the tools call. The
remaining protocols (Files/Contacts/Chat/Issue) describe capabilities no
adapter implements yet; they exist so future adapters (Nextcloud,
FEATURE-NEXTCLOUD-BACKEND.md) have a documented shape to target.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class MailBackend(Protocol):
    """Mirrors the `_imap` duck type in tools/email.py."""

    def fetch(self, criteria: str = "ALL", *, mark_seen: bool = False, limit: int | None = None): ...
    def append(self, msg_bytes: bytes, flags: str, *, folder: str) -> None: ...
    def logout(self) -> None: ...


@runtime_checkable
class CalendarBackend(Protocol):
    """Mirrors the `_dav` duck type in tools/calendar.py."""

    def list_events(self, start: datetime, end: datetime) -> list[dict]: ...
    def find_events(self, start: datetime, end: datetime) -> list[dict]: ...
    def create_event(
        self, uid: str, title: str, start: datetime, end: datetime,
        attendees: list[str] | None = None, location: str | None = None,
        description: str | None = None,
    ) -> dict: ...
    def update_event(self, id: str, **fields) -> dict: ...
    def delete_event(self, id: str) -> None: ...


@runtime_checkable
class FilesBackend(Protocol):
    """Not wired to tools/files.py yet — target shape for a future non-local
    adapter (webdav/Nextcloud/Drive/OneDrive)."""

    def list_files(self, path: str) -> list[dict]: ...
    def read_file(self, path: str) -> str: ...
    def write_file(self, path: str, content: str) -> str: ...
    def search_files(self, query: str, path: str) -> list[dict]: ...


@runtime_checkable
class ContactsBackend(Protocol):
    """No MCP tool consumes this yet — see FEATURE-NEXTCLOUD-BACKEND.md."""

    def search(self, query: str) -> list[dict]: ...
    def get(self, id: str) -> dict: ...


@runtime_checkable
class ChatBackend(Protocol):
    """No MCP tool consumes this yet — a future `chat_post`/`chat_read`."""

    def post(self, channel: str, text: str) -> dict: ...
    def list_messages(self, channel: str, since: datetime) -> list[dict]: ...


@runtime_checkable
class IssueBackend(Protocol):
    """No MCP tool consumes this yet — a future `issue_*` synced with the backlog."""

    def list(self, query: dict) -> list[dict]: ...
    def create(self, item: dict) -> dict: ...
    def update(self, id: str, **fields) -> dict: ...
