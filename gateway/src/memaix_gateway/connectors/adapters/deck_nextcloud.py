# SPDX-License-Identifier: AGPL-3.0-or-later
"""Nextcloud Deck REST client, behind the connector framework
(FEATURE-NEXTCLOUD-BACKEND.md §7 — Deck ↔ backlog sync).

Deck isn't an open protocol like WebDAV/CardDAV/CalDAV — it's Nextcloud's
own OCS-style JSON REST API (`/apps/deck/api/v1.0/...`), so this adapter
talks JSON directly rather than parsing XML/vCard/iCal like the other three
Nextcloud adapters. Same injectable-`_http` shape for testing without a
real server.
"""

from __future__ import annotations


def _card_to_dict(data: dict) -> dict:
    return {
        "id": data.get("id"),
        "title": data.get("title", ""),
        "description": data.get("description") or "",
        "last_modified": data.get("lastModified", 0),
    }


class DeckAdapter:
    def __init__(self, base_url: str, username: str, password: str, *, _http=None) -> None:
        self._base_url = base_url.rstrip("/") + "/index.php/apps/deck/api/v1.0/"
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

    def list_cards(self, board_id, stack_id) -> list[dict]:
        resp = self._request("GET", f"boards/{board_id}/stacks/{stack_id}")
        resp.raise_for_status()
        return [_card_to_dict(c) for c in resp.json().get("cards", [])]

    def get_card(self, board_id, stack_id, card_id) -> dict:
        resp = self._request("GET", f"boards/{board_id}/stacks/{stack_id}/cards/{card_id}")
        resp.raise_for_status()
        return _card_to_dict(resp.json())

    def create_card(self, board_id, stack_id, title: str, description: str = "") -> dict:
        resp = self._request(
            "POST", f"boards/{board_id}/stacks/{stack_id}/cards",
            json={"title": title, "description": description, "type": "plain"},
        )
        resp.raise_for_status()
        return _card_to_dict(resp.json())

    def update_card(self, board_id, stack_id, card_id, *, title: str | None = None, description: str | None = None) -> dict:
        current = self.get_card(board_id, stack_id, card_id)
        body = {
            "title": title if title is not None else current["title"],
            "description": description if description is not None else current["description"],
        }
        resp = self._request("PUT", f"boards/{board_id}/stacks/{stack_id}/cards/{card_id}", json=body)
        resp.raise_for_status()
        return _card_to_dict(resp.json())
