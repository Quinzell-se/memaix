# SPDX-License-Identifier: AGPL-3.0-or-later
"""CardDAV ContactsBackend — Nextcloud (or any CardDAV server) address book
lookup, behind the connector framework (FEATURE-NEXTCLOUD-BACKEND.md §5).

Scope: read-only search/get. Rather than hand-rolling a CardDAV
addressbook-query REPORT (namespaced XML request body), this lists the
address book via PROPFIND, fetches each vCard, and filters in Python —
the same pragmatic "fetch + parse + filter locally" shape tools/calendar.py
already uses for its iCal adapter (_ICalAdapter), and it's simple enough to
test against a small mocked HTTP client without a real Nextcloud in CI.
"""

from __future__ import annotations

import defusedxml.ElementTree as ET


def _vcard_to_dict(card) -> dict:
    def _first(prop) -> str:
        if prop is None:
            return ""
        value = prop.value
        if isinstance(value, list):
            value = value[0] if value else ""
        return str(value) if value else ""

    fn = _first(getattr(card, "fn", None))
    email = _first(getattr(card, "email", None))
    org = _first(getattr(card, "org", None))
    tel = _first(getattr(card, "tel", None))
    uid = _first(getattr(card, "uid", None)) or email or fn
    return {"id": uid, "name": fn, "email": email, "org": org, "phone": tel}


class CardDavContactsAdapter:
    """Implements connectors.base.ContactsBackend against a CardDAV collection."""

    def __init__(self, base_url: str, username: str, password: str, *, _http=None) -> None:
        self._base_url = base_url.rstrip("/") + "/"
        self._username = username
        self._password = password
        self._http = _http  # injected for tests: object with .request(method, url, **kw)

    def _request(self, method: str, path: str = "", **kwargs):
        url = self._base_url + path.lstrip("/") if path else self._base_url
        if self._http is not None:
            return self._http.request(method, url, **kwargs)
        import requests

        return requests.request(method, url, auth=(self._username, self._password), timeout=10, **kwargs)

    def _list_vcard_hrefs(self) -> list[str]:
        body = '<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:getetag/></d:prop></d:propfind>'
        resp = self._request(
            "PROPFIND", headers={"Depth": "1", "Content-Type": "application/xml"}, data=body
        )
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        return [
            elem.text for elem in root.iter()
            if elem.tag.endswith("href") and elem.text and elem.text.endswith(".vcf")
        ]

    def _fetch_vcard(self, href: str) -> dict | None:
        import vobject

        resp = self._request("GET", href)
        resp.raise_for_status()
        try:
            card = vobject.readOne(resp.text)
        except Exception:
            return None
        return _vcard_to_dict(card)

    def _all_contacts(self) -> list[dict]:
        contacts = []
        for href in self._list_vcard_hrefs():
            parsed = self._fetch_vcard(href)
            if parsed:
                contacts.append(parsed)
        return contacts

    def search(self, query: str) -> list[dict]:
        q = query.lower()
        return [
            c for c in self._all_contacts()
            if q in " ".join(v for v in c.values() if v).lower()
        ]

    def get(self, id: str) -> dict:
        for c in self._all_contacts():
            if c["id"] == id:
                return c
        raise FileNotFoundError(f"contact not found: {id!r}")
