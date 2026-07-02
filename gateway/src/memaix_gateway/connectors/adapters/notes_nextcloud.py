# SPDX-License-Identifier: AGPL-3.0-or-later
"""Nextcloud Notes REST client, behind the connector framework
(FEATURE-NEXTCLOUD-BACKEND.md §7 — Notes <-> memory sync).

Same shape as deck_nextcloud.py: Notes is Nextcloud's own JSON REST API
(`/apps/notes/api/v1/...`), not an open DAV protocol, so this speaks JSON
directly with an injectable `_http` for testing without a real server.
"""

from __future__ import annotations


def _note_to_dict(data: dict) -> dict:
    return {
        "id": data.get("id"),
        "title": data.get("title", ""),
        "content": data.get("content") or "",
        "last_modified": data.get("modified", 0),
    }


class NotesAdapter:
    def __init__(self, base_url: str, username: str, password: str, *, _http=None) -> None:
        self._base_url = base_url.rstrip("/") + "/index.php/apps/notes/api/v1/"
        self._username = username
        self._password = password
        self._http = _http  # injected for tests: object with .request(method, url, **kw)

    def _request(self, method: str, path: str, **kwargs):
        headers = kwargs.pop("headers", {})
        headers.setdefault("OCS-APIRequest", "true")
        headers.setdefault("Content-Type", "application/json")
        url = self._base_url + path
        if self._http is not None:
            return self._http.request(method, url, headers=headers, **kwargs)
        import requests

        return requests.request(
            method, url, auth=(self._username, self._password), headers=headers, timeout=15, **kwargs
        )

    def list_notes(self) -> list[dict]:
        resp = self._request("GET", "notes")
        resp.raise_for_status()
        return [_note_to_dict(n) for n in resp.json()]

    def get_note(self, note_id) -> dict:
        resp = self._request("GET", f"notes/{note_id}")
        resp.raise_for_status()
        return _note_to_dict(resp.json())

    def create_note(self, title: str, content: str = "") -> dict:
        resp = self._request("POST", "notes", json={"title": title, "content": content})
        resp.raise_for_status()
        return _note_to_dict(resp.json())

    def update_note(self, note_id, *, title: str | None = None, content: str | None = None) -> dict:
        current = self.get_note(note_id)
        body = {
            "title": title if title is not None else current["title"],
            "content": content if content is not None else current["content"],
        }
        resp = self._request("PUT", f"notes/{note_id}", json=body)
        resp.raise_for_status()
        return _note_to_dict(resp.json())
