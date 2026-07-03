# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for calendar.setup_mode (MEX-020) — the extracted setup path.

Focus: the SSRF guard on the user-supplied iCal secret URL must reject internal
targets at configuration time, before the URL is ever stored or fetched. This
guards against the regression where the extraction dropped the inline check.
"""

from __future__ import annotations

import pytest

from memaix_gateway.acl import Acl
from memaix_gateway.tools.calendar import get_status, setup_mode


class _FakeStore:
    """Minimal duck-type of the token store used by setup_mode/get_status."""

    def __init__(self) -> None:
        self.records: dict[tuple, dict] = {}

    def store(self, user_id, provider, account, data):
        self.records[(user_id, provider, account)] = data

    def delete(self, user_id, provider, account):
        self.records.pop((user_id, provider, account), None)

    def list_accounts(self, user_id):
        return [
            {"provider": p, "account": a, "status": "ok"}
            for (u, p, a) in self.records
            if u == user_id
        ]

    def load_one(self, user_id, provider, account):
        return self.records.get((user_id, provider, account))


@pytest.fixture()
def acl():
    return Acl(
        users={"alice": {"grants": {"acme": "owner"}}},
        projects={"acme": {"vault": "/tmp/acme"}},
    )


@pytest.fixture()
def store():
    return _FakeStore()


@pytest.mark.parametrize(
    "bad_url",
    [
        # Literal internal IPs and non-http schemes are caught at config time
        # (the literal-IP / scheme checks run even with resolve=False).
        "http://127.0.0.1/secret.ics",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/cal.ics",
        "http://192.168.1.1/cal.ics",
        "file:///etc/passwd",
        "ftp://internal/cal.ics",
    ],
)
def test_ical_secret_rejects_internal_or_nonhttp_url(acl, store, bad_url):
    result = setup_mode(acl, "alice", "acme", "ical_secret", store, "", ical_url=bad_url)
    assert result["ok"] is False
    assert "avvisad" in result["error"]
    # Nothing must have been stored.
    assert store.records == {}


def test_ical_fetch_blocks_internal_hostname():
    """A hostname that resolves to a private/loopback address (e.g. localhost)
    is caught at fetch time — config time skips DNS by design, so the
    authoritative resolve lives in _ICalAdapter._fetch."""
    from memaix_gateway.safety.net import BlockedURLError
    from memaix_gateway.tools.calendar import _ICalAdapter

    adapter = _ICalAdapter("http://localhost/secret.ics")
    with pytest.raises(BlockedURLError):
        adapter._fetch()


def test_ical_secret_accepts_external_url(acl, store):
    url = "https://calendar.google.com/calendar/ical/abc/basic.ics"
    result = setup_mode(acl, "alice", "acme", "ical_secret", store, "", ical_url=url)
    assert result["ok"] is True
    assert result["stored"] is True
    assert store.records[("alice", "ical_secret", "ical_secret")] == {"ical_url": url}


def test_ical_secret_requires_url(acl, store):
    result = setup_mode(acl, "alice", "acme", "ical_secret", store, "", ical_url=None)
    assert result["ok"] is False
    assert store.records == {}


def test_setup_mode_enforces_acl(acl, store):
    from memaix_gateway.acl import AccessDenied

    with pytest.raises(AccessDenied):
        setup_mode(acl, "mallory", "acme", "ical_secret", store, "",
                   ical_url="https://calendar.google.com/x.ics")


def test_status_reflects_configured_ical(acl, store):
    setup_mode(acl, "alice", "acme", "ical_secret", store, "",
               ical_url="https://calendar.google.com/x.ics")
    status = get_status("alice", "acme", acl, store)
    assert status["active_mode"] == "ical_secret"
