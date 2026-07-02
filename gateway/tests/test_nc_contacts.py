# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the CardDAV ContactsBackend adapter — FEATURE-NEXTCLOUD-BACKEND.md §5."""

from __future__ import annotations

import pytest

from memaix_gateway.connectors.adapters.contacts_carddav import CardDavContactsAdapter

PROPFIND_RESPONSE = """<?xml version="1.0"?>
<d:multistatus xmlns:d="DAV:">
  <d:response>
    <d:href>/dav/addressbooks/users/alice/contacts/anna.vcf</d:href>
    <d:propstat><d:prop><d:getetag>"1"</d:getetag></d:prop></d:propstat>
  </d:response>
  <d:response>
    <d:href>/dav/addressbooks/users/alice/contacts/erik.vcf</d:href>
    <d:propstat><d:prop><d:getetag>"2"</d:getetag></d:prop></d:propstat>
  </d:response>
  <d:response>
    <d:href>/dav/addressbooks/users/alice/contacts/</d:href>
    <d:propstat><d:prop><d:getetag/></d:prop></d:propstat>
  </d:response>
</d:multistatus>
"""

ANNA_VCARD = (
    "BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Anna Andersson\r\nEMAIL:anna@acme.com\r\n"
    "ORG:Acme AB\r\nTEL:+46701234567\r\nUID:anna-uid\r\nEND:VCARD\r\n"
)
ERIK_VCARD = (
    "BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Erik Eriksson\r\nEMAIL:erik@acme.com\r\n"
    "ORG:Acme AB\r\nUID:erik-uid\r\nEND:VCARD\r\n"
)


class _FakeResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeHttp:
    def __init__(self, propfind=PROPFIND_RESPONSE, vcards=None):
        self._propfind = propfind
        self._vcards = vcards or {}
        self.requests: list[tuple[str, str]] = []

    def request(self, method, url, **kwargs):
        self.requests.append((method, url))
        if method == "PROPFIND":
            return _FakeResponse(self._propfind)
        for suffix, body in self._vcards.items():
            if url.endswith(suffix):
                return _FakeResponse(body)
        return _FakeResponse("", status_code=404)


@pytest.fixture()
def adapter():
    http = _FakeHttp(vcards={"anna.vcf": ANNA_VCARD, "erik.vcf": ERIK_VCARD})
    return CardDavContactsAdapter("https://nc.example.com/dav/addressbooks/users/alice/contacts/", "alice", "secret", _http=http), http


def test_search_matches_by_name(adapter):
    a, _http = adapter
    results = a.search("anna")
    assert len(results) == 1
    assert results[0]["email"] == "anna@acme.com"
    assert results[0]["org"] == "Acme AB"
    assert results[0]["phone"] == "+46701234567"


def test_search_matches_by_email_case_insensitive(adapter):
    a, _http = adapter
    results = a.search("ERIK@ACME.COM")
    assert len(results) == 1
    assert results[0]["id"] == "erik-uid"


def test_search_matches_by_org_returns_all(adapter):
    a, _http = adapter
    results = a.search("acme ab")
    assert {r["id"] for r in results} == {"anna-uid", "erik-uid"}


def test_search_no_match_returns_empty(adapter):
    a, _http = adapter
    assert a.search("nonexistent") == []


def test_get_by_id_returns_contact(adapter):
    a, _http = adapter
    contact = a.get("anna-uid")
    assert contact["name"] == "Anna Andersson"


def test_get_unknown_id_raises_not_found(adapter):
    a, _http = adapter
    with pytest.raises(FileNotFoundError):
        a.get("nope")


def test_propfind_ignores_collection_href_without_vcf_suffix(adapter):
    a, http = adapter
    a.search("anna")
    vcf_fetches = [u for m, u in http.requests if m == "GET"]
    assert all(u.endswith(".vcf") for u in vcf_fetches)


def test_uses_real_requests_when_no_http_injected(monkeypatch):
    calls = []

    class _FakeRequests:
        @staticmethod
        def request(method, url, auth=None, timeout=None, **kwargs):
            calls.append((method, url, auth))
            return _FakeResponse(PROPFIND_RESPONSE)

    import sys

    monkeypatch.setitem(sys.modules, "requests", _FakeRequests)
    a = CardDavContactsAdapter("https://nc.example.com/contacts/", "bob", "pw")
    a._list_vcard_hrefs()
    assert calls[0][0] == "PROPFIND"
    assert calls[0][2] == ("bob", "pw")
