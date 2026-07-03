# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the CalDAV VTODO TasksBackend adapter — FEATURE-NEXTCLOUD-BACKEND.md §3."""

from __future__ import annotations

import pytest

from memaix_gateway.connectors.adapters.tasks_caldav import CalDavTasksAdapter

def _propfind_for(names: list[str]) -> str:
    responses = "".join(
        f'<d:response><d:href>/dav/tasks/alice/{name}</d:href>'
        f"<d:propstat><d:prop><d:getetag/></d:prop></d:propstat></d:response>"
        for name in [*names, ""]  # trailing "" -> the collection itself
    )
    return f'<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">{responses}</d:multistatus>'


FOLLOWUP_VTODO = (
    "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VTODO\r\nUID:follow-up\r\n"
    "SUMMARY:Follow up with client\r\nSTATUS:NEEDS-ACTION\r\nEND:VTODO\r\nEND:VCALENDAR\r\n"
)
INVOICE_VTODO = (
    "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VTODO\r\nUID:invoice\r\n"
    "SUMMARY:Send invoice\r\nSTATUS:NEEDS-ACTION\r\nDUE:20250201T000000\r\nEND:VTODO\r\nEND:VCALENDAR\r\n"
)


class _FakeResponse:
    def __init__(self, text: str = "", status_code: int = 200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeHttp:
    def __init__(self, vtodos=None):
        self._vtodos = dict(vtodos or {})
        self.requests: list[tuple[str, str]] = []

    def request(self, method, url, **kwargs):
        self.requests.append((method, url))
        if method == "PROPFIND":
            return _FakeResponse(_propfind_for(list(self._vtodos.keys())))
        if method == "GET":
            for suffix, body in self._vtodos.items():
                if url.endswith(suffix):
                    return _FakeResponse(body)
            return _FakeResponse("", status_code=404)
        if method == "PUT":
            name = url.rsplit("/", 1)[-1]
            self._vtodos[name] = kwargs.get("data", b"").decode("utf-8")
            return _FakeResponse("")
        return _FakeResponse("", status_code=405)


@pytest.fixture()
def http():
    return _FakeHttp(vtodos={"follow-up.ics": FOLLOWUP_VTODO, "invoice.ics": INVOICE_VTODO})


@pytest.fixture()
def adapter(http):
    return CalDavTasksAdapter("https://nc.example.com/dav/tasks/alice/", "alice", "secret", _http=http)


def test_list_returns_all_tasks(adapter):
    tasks = adapter.list()
    ids = {t["id"] for t in tasks}
    assert ids == {"follow-up", "invoice"}


def test_list_parses_fields(adapter):
    tasks = {t["id"]: t for t in adapter.list()}
    assert tasks["invoice"]["title"] == "Send invoice"
    assert tasks["invoice"]["due"] == "2025-02-01 00:00:00"
    assert tasks["invoice"]["completed"] is False


def test_add_creates_new_task(adapter, http):
    result = adapter.add("Call supplier", due="2025-03-01", notes="ask about pricing")
    assert result["title"] == "Call supplier"
    assert result["completed"] is False
    assert any(m == "PUT" for m, _u in http.requests)


def test_add_new_task_is_then_listed(adapter):
    adapter.add("Call supplier")
    tasks = adapter.list()
    assert any(t["title"] == "Call supplier" for t in tasks)


def test_complete_marks_task_done(adapter):
    result = adapter.complete("follow-up")
    assert result["completed"] is True
    # re-fetch to confirm persistence
    tasks = {t["id"]: t for t in adapter.list()}
    assert tasks["follow-up"]["completed"] is True


def test_complete_unknown_task_raises(adapter):
    with pytest.raises(FileNotFoundError):
        adapter.complete("nonexistent")
