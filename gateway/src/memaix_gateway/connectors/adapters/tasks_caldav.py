# SPDX-License-Identifier: AGPL-3.0-or-later
"""CalDAV VTODO TasksBackend — Nextcloud (or any CalDAV server) task lists,
behind the connector framework (FEATURE-NEXTCLOUD-BACKEND.md §3, Byggordning
step 5).

Same "PROPFIND to list, GET+parse each with vobject, mutate/filter locally"
shape as contacts_carddav.py and files_webdav.py — consistent across the
three Nextcloud adapters and simple to test without a real server.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import defusedxml.ElementTree as ET


def _first(prop) -> str:
    if prop is None:
        return ""
    value = prop.value
    return str(value) if value else ""


def _todo_to_dict(vtodo) -> dict:
    status = _first(getattr(vtodo, "status", None)) or "NEEDS-ACTION"
    return {
        "id": _first(getattr(vtodo, "uid", None)),
        "title": _first(getattr(vtodo, "summary", None)),
        "due": _first(getattr(vtodo, "due", None)),
        "notes": _first(getattr(vtodo, "description", None)),
        "completed": status == "COMPLETED",
    }


class CalDavTasksAdapter:
    """Implements connectors.base.TasksBackend against a CalDAV VTODO collection."""

    def __init__(self, base_url: str, username: str, password: str, *, _http=None) -> None:
        self._base_url = base_url.rstrip("/") + "/"
        self._username = username
        self._password = password
        self._http = _http  # injected for tests: object with .request(method, url, **kw)

    def _request(self, method: str, path: str = "", **kwargs):
        url = self._base_url + path if path else self._base_url
        if self._http is not None:
            return self._http.request(method, url, **kwargs)
        import requests

        return requests.request(method, url, auth=(self._username, self._password), timeout=15, **kwargs)

    def _list_hrefs(self) -> list[str]:
        body = '<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:getetag/></d:prop></d:propfind>'
        resp = self._request("PROPFIND", headers={"Depth": "1", "Content-Type": "application/xml"}, data=body)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        return [
            elem.text for elem in root.iter()
            if elem.tag.endswith("href") and elem.text and elem.text.endswith(".ics")
        ]

    def _fetch_calendar(self, href: str):
        import vobject

        try:
            resp = self._request("GET", href)
            resp.raise_for_status()
        except Exception:
            return None  # gone/unreadable — callers treat this as "not found"
        try:
            return vobject.readOne(resp.text)
        except Exception:
            return None

    def _vtodo_of(self, cal):
        if cal is None:
            return None
        return next((c for c in cal.components() if c.name == "VTODO"), None)

    def list(self) -> list[dict]:
        tasks = []
        for href in self._list_hrefs():
            vtodo = self._vtodo_of(self._fetch_calendar(href))
            if vtodo is not None:
                tasks.append(_todo_to_dict(vtodo))
        return tasks

    def add(self, title: str, due: str | None = None, notes: str | None = None) -> dict:
        import vobject

        cal = vobject.iCalendar()
        vtodo = cal.add("vtodo")
        task_id = uuid.uuid4().hex
        vtodo.add("uid").value = task_id
        vtodo.add("summary").value = title
        vtodo.add("status").value = "NEEDS-ACTION"
        if due:
            vtodo.add("due").value = datetime.fromisoformat(due)
        if notes:
            vtodo.add("description").value = notes

        resp = self._request(
            "PUT", f"{task_id}.ics", data=cal.serialize().encode("utf-8"), headers={"Content-Type": "text/calendar"}
        )
        resp.raise_for_status()
        return _todo_to_dict(vtodo)

    def complete(self, id: str) -> dict:
        href = f"{id}.ics"
        cal = self._fetch_calendar(href)
        vtodo = self._vtodo_of(cal)
        if vtodo is None:
            raise FileNotFoundError(f"task not found: {id!r}")

        # vobject can't serialize a datetime.timezone.utc-aware value (it
        # only recognizes pytz-style tzinfo for TZID lookup) — use a naive
        # UTC wall-clock value instead, same as iCalendar's floating-UTC
        # convention for auto-generated DTSTAMP.
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        if hasattr(vtodo, "status"):
            vtodo.status.value = "COMPLETED"
        else:
            vtodo.add("status").value = "COMPLETED"
        if hasattr(vtodo, "completed"):
            vtodo.completed.value = now_utc
        else:
            vtodo.add("completed").value = now_utc

        resp = self._request(
            "PUT", href, data=cal.serialize().encode("utf-8"), headers={"Content-Type": "text/calendar"}
        )
        resp.raise_for_status()
        return _todo_to_dict(vtodo)
