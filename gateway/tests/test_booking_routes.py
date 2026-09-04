# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the public /book/{slug} routes — memaix-src card 2bef1062."""

from __future__ import annotations

import functools
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest
from starlette.testclient import TestClient

from memaix_gateway import config
from memaix_gateway.acl import Acl
from memaix_gateway.connectors.booking_settings import BookingSettingsStore
from memaix_gateway.tools import email as email_mod


def _dt(h: int, m: int = 0) -> datetime:
    return datetime(2026, 1, 3, h, m, tzinfo=timezone.utc)


class _MockDav:
    def __init__(self, events=None):
        self._events = list(events or [])

    def list_events(self, start, end):
        return [e for e in self._events if _parse(e["start"]) >= start and _parse(e["end"]) <= end]

    find_events = list_events

    def create_event(self, uid, title, start, end, attendees=None, location=None, description=None):
        ev = {"id": uid, "title": title, "start": start.isoformat(), "end": end.isoformat(), "description": description}
        self._events.append(ev)
        return ev


def _parse(s):
    return datetime.fromisoformat(s) if isinstance(s, str) else s


class _MockSmtp:
    def __init__(self) -> None:
        self.sent: list = []

    def send_message(self, msg) -> None:
        self.sent.append(msg)


@pytest.fixture()
def rig(tmp_path, monkeypatch):
    from memaix_gateway import server as server_mod

    vault = tmp_path / "vault"
    smtp = _MockSmtp()
    acl = Acl(
        users={"alice": {"grants": {"proj": "owner"}}},
        projects={"proj": {
            "vault": str(vault),
            "calendar": {"type": "caldav"},
            "mailbox": {"host": "imap.example.com", "user": "alice@example.com", "password_ref": "env:FAKE_MAILBOX_PW"},
            "allow_send": True,
        }},
    )
    monkeypatch.setenv("FAKE_MAILBOX_PW", "shh")
    import memaix_gateway.booking.routes as booking_routes_mod
    monkeypatch.setattr(
        booking_routes_mod.t_email, "email_send",
        functools.partial(email_mod.email_send, _smtp=smtp),
    )
    monkeypatch.setattr(server_mod, "_acl", acl)
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)

    links_dir = tmp_path / "booking_links"
    links_dir.mkdir(parents=True)
    (links_dir / "alice-30.json").write_text(json.dumps({
        "project": "proj", "user": "alice", "duration_min": 30, "title_template": "Möte med {name}",
        "host_email": "alice@example.com", "host_timezone": "Europe/Stockholm",
    }))

    BookingSettingsStore(acl, "proj", "alice").set(True)

    dav = _MockDav()
    monkeypatch.setattr(server_mod, "_resolve_calendar_dav", lambda project, user: dav)

    monkeypatch.setenv("TEST_TURNSTILE_SECRET", "shh")
    monkeypatch.setattr(config, "load", lambda: {"memaix": {"booking": {"turnstile_secret_ref": "env:TEST_TURNSTILE_SECRET"}}})

    class _FakeTurnstileResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"success": True}

    class _FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *a, **kw):
            return _FakeTurnstileResponse()

    import memaix_gateway.booking.routes as booking_routes_mod
    monkeypatch.setattr(booking_routes_mod.httpx, "AsyncClient", lambda *a, **kw: _FakeAsyncClient())

    app = server_mod.build_http_app()
    client = TestClient(app)
    client.smtp = smtp
    return client, dav


def test_unknown_slug_is_404(rig):
    client, _dav = rig
    resp = client.get("/book/no-such-slug/slots?within_start=2026-01-03T08:00:00+00:00&within_end=2026-01-03T18:00:00+00:00")
    assert resp.status_code == 404


def test_slots_returns_only_start_end(rig):
    client, dav = rig
    dav.create_event("ev1", "Secret", _dt(9), _dt(9, 30))
    resp = client.get(
        "/book/alice-30/slots",
        params={"within_start": _dt(8).isoformat(), "within_end": _dt(18).isoformat()},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "slots" in body
    for slot in body["slots"]:
        assert set(slot.keys()) == {"start", "end"}


def test_slots_404_when_booking_disabled(rig, monkeypatch):
    client, _dav = rig
    from memaix_gateway import server as server_mod
    BookingSettingsStore(server_mod._acl, "proj", "alice").set(False)
    resp = client.get(
        "/book/alice-30/slots",
        params={"within_start": _dt(8).isoformat(), "within_end": _dt(18).isoformat()},
    )
    assert resp.status_code == 404


def test_create_booking_succeeds_and_stores_event(rig):
    client, dav = rig
    resp = client.post(
        "/book/alice-30",
        json={
            "start": _dt(10).isoformat(), "end": _dt(10, 30).isoformat(),
            "name": "Bob", "email": "bob@example.com", "turnstile_token": "tok",
            "consent": True, "consent_text": "Jag samtycker till lagring i 1 år.",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert any(e["title"] == "Möte med Bob" for e in dav._events)


def test_create_booking_without_consent_is_rejected(rig):
    client, dav = rig
    resp = client.post(
        "/book/alice-30",
        json={
            "start": _dt(19).isoformat(), "end": _dt(19, 30).isoformat(),
            "name": "Bob", "email": "bob@example.com", "turnstile_token": "tok",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "consent_required"
    assert not any(e["start"] == _dt(19).isoformat() for e in dav._events)


def test_create_booking_records_consent(rig, monkeypatch, tmp_path):
    from memaix_gateway.booking.consent_store import ConsentStore
    import memaix_gateway.booking.routes as booking_routes_mod

    store = ConsentStore(tmp_path / "consent.db")
    monkeypatch.setattr(booking_routes_mod, "get_consent_store", lambda: store)

    client, dav = rig
    resp = client.post(
        "/book/alice-30",
        json={
            "start": _dt(20).isoformat(), "end": _dt(20, 30).isoformat(),
            "name": "Bob", "email": "bob@example.com", "turnstile_token": "tok",
            "consent": True, "consent_text": "Jag samtycker.",
        },
    )
    assert resp.status_code == 200
    rows = store.due(int(_dt(20, 30).timestamp()) + 366 * 86400)
    assert len(rows) == 1
    assert rows[0]["project"] == "proj"
    assert rows[0]["host_user"] == "alice"
    assert rows[0]["visitor_email"] == "bob@example.com"


def test_create_booking_passes_purpose_as_description(rig):
    client, dav = rig
    resp = client.post(
        "/book/alice-30",
        json={
            "start": _dt(13).isoformat(), "end": _dt(13, 30).isoformat(),
            "name": "Bob", "email": "bob@example.com", "turnstile_token": "tok",
            "purpose": "Prata om samarbete kring X.", "consent": True,
        },
    )
    assert resp.status_code == 200
    ev = next(e for e in dav._events if e["start"] == _dt(13).isoformat())
    assert ev["description"] == "Prata om samarbete kring X."


def test_create_booking_without_purpose_stores_no_description(rig):
    client, dav = rig
    resp = client.post(
        "/book/alice-30",
        json={
            "start": _dt(14).isoformat(), "end": _dt(14, 30).isoformat(),
            "name": "Bob", "email": "bob@example.com", "turnstile_token": "tok",
            "consent": True,
        },
    )
    assert resp.status_code == 200
    ev = next(e for e in dav._events if e["start"] == _dt(14).isoformat())
    assert ev["description"] is None


def test_create_booking_truncates_overlong_purpose(rig):
    client, dav = rig
    resp = client.post(
        "/book/alice-30",
        json={
            "start": _dt(15).isoformat(), "end": _dt(15, 30).isoformat(),
            "name": "Bob", "email": "bob@example.com", "turnstile_token": "tok",
            "purpose": "x" * 900, "consent": True,
        },
    )
    assert resp.status_code == 200
    ev = next(e for e in dav._events if e["start"] == _dt(15).isoformat())
    assert len(ev["description"]) == 500


def test_create_booking_sends_confirmation_to_visitor_and_host(rig):
    client, dav = rig
    from memaix_gateway.safety.rate_limit import rate_limiter
    rate_limiter._windows.pop("booking:testclient", None)
    resp = client.post(
        "/book/alice-30",
        json={
            "start": _dt(9).isoformat(), "end": _dt(9, 30).isoformat(),
            "name": "Bob", "email": "bob@example.com", "turnstile_token": "tok",
            "purpose": "Prata om X.", "timezone": "Europe/Stockholm", "consent": True,
        },
    )
    assert resp.status_code == 200
    assert len(client.smtp.sent) == 2
    recipients = {msg["To"] for msg in client.smtp.sent}
    assert recipients == {"bob@example.com", "alice@example.com"}
    for msg in client.smtp.sent:
        attachments = list(msg.iter_attachments())
        assert len(attachments) == 1
        assert attachments[0].get_filename() == "moete.ics"
        ics_content = attachments[0].get_content()
        ics_text = ics_content.decode("utf-8") if isinstance(ics_content, bytes) else ics_content
        assert "BEGIN:VEVENT" in ics_text
        assert "Prata om X." in msg.get_body(preferencelist=("plain",)).get_content()


def test_create_booking_without_host_email_only_emails_visitor(rig, tmp_path):
    client, dav = rig
    from memaix_gateway import config
    from memaix_gateway.safety.rate_limit import rate_limiter
    rate_limiter._windows.pop("booking:testclient", None)
    (config.CONFIG_DIR / "booking_links" / "no-host-email.json").write_text(json.dumps({
        "project": "proj", "user": "alice", "duration_min": 30, "title_template": "Möte",
    }))
    resp = client.post(
        "/book/no-host-email",
        json={
            "start": _dt(17).isoformat(), "end": _dt(17, 30).isoformat(),
            "name": "Bob", "email": "bob@example.com", "turnstile_token": "tok",
            "consent": True,
        },
    )
    assert resp.status_code == 200
    assert len(client.smtp.sent) == 1
    assert client.smtp.sent[0]["To"] == "bob@example.com"


def test_create_booking_succeeds_even_if_confirmation_email_fails(rig, monkeypatch):
    client, dav = rig
    import memaix_gateway.booking.routes as booking_routes_mod
    from memaix_gateway.safety.rate_limit import rate_limiter
    rate_limiter._windows.pop("booking:testclient", None)

    def _boom(*a, **kw):
        raise RuntimeError("smtp exploded")

    monkeypatch.setattr(booking_routes_mod.t_email, "email_send", _boom)
    resp = client.post(
        "/book/alice-30",
        json={
            "start": _dt(18).isoformat(), "end": _dt(18, 30).isoformat(),
            "name": "Bob", "email": "bob@example.com", "turnstile_token": "tok",
            "consent": True,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_create_booking_rejects_when_slot_no_longer_free(rig):
    client, dav = rig
    dav._events.append({"id": "ev-taken", "title": "Taken", "start": _dt(10).isoformat(), "end": _dt(10, 30).isoformat()})
    resp = client.post(
        "/book/alice-30",
        json={
            "start": _dt(10).isoformat(), "end": _dt(10, 30).isoformat(),
            "name": "Bob", "email": "bob@example.com", "turnstile_token": "tok",
            "consent": True,
        },
    )
    assert resp.status_code == 409


def test_concurrent_bookings_for_same_slot_only_one_wins(rig):
    # Card d99e2840: pins the required outcome — of two visitors racing for
    # the identical slot, exactly one gets 200 and the other gets 409
    # slot_unavailable, never two overlapping events. This is a result
    # assertion, not proof the _BOOKING_LOCKS lock itself is exercised: with
    # TestClient, booking_create's async handler already serializes on the
    # event loop (no await inside the critical section), so this passes
    # regardless of the lock. What it does guard is the TOCTOU re-check
    # logic never regressing to let both requests through.
    client, dav = rig
    # The module-level rate limiter's window is shared across every test in
    # this file (same client_ip) — clear it so the two concurrent requests
    # below are judged only against this test's own traffic, not the POSTs
    # already made by earlier tests in the module.
    from memaix_gateway.safety.rate_limit import rate_limiter
    rate_limiter._windows.pop("booking:testclient", None)

    payload = {
        "start": _dt(16).isoformat(), "end": _dt(16, 30).isoformat(),
        "name": "Bob", "email": "bob@example.com", "turnstile_token": "tok",
        "consent": True,
    }

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(client.post, "/book/alice-30", json=payload) for _ in range(2)]
        responses = [f.result() for f in futures]

    statuses = sorted(r.status_code for r in responses)
    assert statuses == [200, 409]
    matching = [e for e in dav._events if e["start"] == _dt(16).isoformat()]
    assert len(matching) == 1


def test_create_booking_fails_closed_without_turnstile_configured(rig, monkeypatch):
    client, _dav = rig
    monkeypatch.setattr(config, "load", lambda: {"memaix": {}})
    resp = client.post(
        "/book/alice-30",
        json={
            "start": _dt(11).isoformat(), "end": _dt(11, 30).isoformat(),
            "name": "Bob", "email": "bob@example.com", "turnstile_token": "tok",
        },
    )
    assert resp.status_code == 403
    assert resp.json()["error"] == "captcha_failed"


def test_create_booking_rejects_missing_fields(rig):
    client, _dav = rig
    resp = client.post("/book/alice-30", json={"start": _dt(12).isoformat(), "turnstile_token": "tok"})
    assert resp.status_code == 400


def test_cors_headers_present_for_allowed_origin(rig):
    client, _dav = rig
    resp = client.get(
        "/book/alice-30/slots",
        params={"within_start": _dt(8).isoformat(), "within_end": _dt(18).isoformat()},
        headers={"Origin": "https://jimlov.se"},
    )
    assert resp.headers["access-control-allow-origin"] == "https://jimlov.se"


def test_cors_headers_absent_for_disallowed_origin(rig):
    client, _dav = rig
    resp = client.get(
        "/book/alice-30/slots",
        params={"within_start": _dt(8).isoformat(), "within_end": _dt(18).isoformat()},
        headers={"Origin": "https://evil.example"},
    )
    assert "access-control-allow-origin" not in resp.headers


def test_real_browser_preflight_reaches_booking_handler_not_app_wide_cors(rig):
    # A real browser preflights any POST with Content-Type: application/json
    # by sending OPTIONS with Access-Control-Request-Method — unlike a bare
    # Origin header (see test_cors_headers_present_for_allowed_origin above),
    # this is what actually exercises the app-wide CORSMiddleware's own
    # preflight interception (Simon's review on card 2bef1062: that
    # middleware only knows claude.ai and would 400 this before it ever
    # reaches booking/routes.py's own OPTIONS handler).
    client, _dav = rig
    resp = client.options(
        "/book/alice-30",
        headers={
            "Origin": "https://jimlov.se",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert resp.status_code == 204
    assert resp.headers["access-control-allow-origin"] == "https://jimlov.se"


def test_turnstile_fails_closed_without_secret_ref(monkeypatch):
    import asyncio

    from memaix_gateway.booking.routes import _verify_turnstile
    monkeypatch.setattr(config, "load", lambda: {"memaix": {}})
    assert asyncio.run(_verify_turnstile("some-token", "1.2.3.4")) is False
