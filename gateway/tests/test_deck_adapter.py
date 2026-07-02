# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the Nextcloud Deck REST client adapter —
FEATURE-NEXTCLOUD-BACKEND.md §7."""

from __future__ import annotations

import pytest

from memaix_gateway.connectors.adapters.deck_nextcloud import DeckAdapter


class _FakeResponse:
    def __init__(self, data, status_code: int = 200):
        self._data = data
        self.status_code = status_code

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeHttp:
    def __init__(self):
        self.requests = []
        self.cards = {
            1: {"id": 1, "title": "Follow up", "description": "call the client", "lastModified": 1000},
            2: {"id": 2, "title": "Send invoice", "description": "", "lastModified": 2000},
        }
        self._next_id = 3

    def request(self, method, url, **kwargs):
        self.requests.append((method, url, kwargs))
        if method == "GET" and "/cards/" not in url:
            return _FakeResponse({"cards": list(self.cards.values())})
        if method == "GET":
            card_id = int(url.rsplit("/", 1)[-1])
            return _FakeResponse(self.cards[card_id])
        if method == "POST":
            body = kwargs["json"]
            new_id = self._next_id
            self._next_id += 1
            card = {"id": new_id, "title": body["title"], "description": body["description"], "lastModified": 3000}
            self.cards[new_id] = card
            return _FakeResponse(card)
        if method == "PUT":
            card_id = int(url.rsplit("/", 1)[-1])
            body = kwargs["json"]
            self.cards[card_id].update({"title": body["title"], "description": body["description"], "lastModified": 4000})
            return _FakeResponse(self.cards[card_id])
        return _FakeResponse({}, status_code=405)


@pytest.fixture()
def http():
    return _FakeHttp()


@pytest.fixture()
def adapter(http):
    return DeckAdapter("https://nc.example.com", "alice", "secret", _http=http)


def test_list_cards(adapter):
    cards = adapter.list_cards(1, 2)
    assert {c["title"] for c in cards} == {"Follow up", "Send invoice"}
    assert cards[0]["last_modified"] == 1000


def test_get_card(adapter):
    card = adapter.get_card(1, 2, 1)
    assert card["title"] == "Follow up"


def test_create_card(adapter):
    card = adapter.create_card(1, 2, "New task", "details")
    assert card["title"] == "New task"
    assert card["description"] == "details"


def test_update_card_changes_title_only(adapter):
    updated = adapter.update_card(1, 2, 1, title="Follow up urgently")
    assert updated["title"] == "Follow up urgently"
    assert updated["description"] == "call the client"  # preserved


def test_request_includes_ocs_header(adapter, http):
    adapter.list_cards(1, 2)
    method, url, kwargs = http.requests[0]
    assert kwargs["headers"]["OCS-APIRequest"] == "true"


def test_base_url_includes_deck_api_path():
    a = DeckAdapter("https://nc.example.com/", "u", "p")
    assert a._base_url == "https://nc.example.com/index.php/apps/deck/api/v1.0/"
