# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the Nextcloud Notes REST client adapter —
FEATURE-NEXTCLOUD-BACKEND.md §7."""

from __future__ import annotations

import pytest

from memaix_gateway.connectors.adapters.notes_nextcloud import NotesAdapter


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
        self.notes = {
            1: {"id": 1, "title": "Ideas", "content": "brainstorm list", "modified": 1000},
            2: {"id": 2, "title": "Meeting notes", "content": "", "modified": 2000},
        }
        self._next_id = 3

    def request(self, method, url, **kwargs):
        self.requests.append((method, url, kwargs))
        if method == "GET" and url.endswith("/notes"):
            return _FakeResponse(list(self.notes.values()))
        if method == "GET":
            note_id = int(url.rsplit("/", 1)[-1])
            return _FakeResponse(self.notes[note_id])
        if method == "POST":
            body = kwargs["json"]
            new_id = self._next_id
            self._next_id += 1
            note = {"id": new_id, "title": body["title"], "content": body["content"], "modified": 3000}
            self.notes[new_id] = note
            return _FakeResponse(note)
        if method == "PUT":
            note_id = int(url.rsplit("/", 1)[-1])
            body = kwargs["json"]
            self.notes[note_id].update({"title": body["title"], "content": body["content"], "modified": 4000})
            return _FakeResponse(self.notes[note_id])
        return _FakeResponse({}, status_code=405)


@pytest.fixture()
def http():
    return _FakeHttp()


@pytest.fixture()
def adapter(http):
    return NotesAdapter("https://nc.example.com", "alice", "secret", _http=http)


def test_list_notes(adapter):
    notes = adapter.list_notes()
    assert {n["title"] for n in notes} == {"Ideas", "Meeting notes"}


def test_get_note(adapter):
    note = adapter.get_note(1)
    assert note["content"] == "brainstorm list"


def test_create_note(adapter):
    note = adapter.create_note("New note", "some content")
    assert note["title"] == "New note"
    assert note["content"] == "some content"


def test_update_note_content_only(adapter):
    updated = adapter.update_note(1, content="revised")
    assert updated["content"] == "revised"
    assert updated["title"] == "Ideas"  # preserved


def test_base_url_includes_notes_api_path():
    a = NotesAdapter("https://nc.example.com/", "u", "p")
    assert a._base_url == "https://nc.example.com/index.php/apps/notes/api/v1/"
