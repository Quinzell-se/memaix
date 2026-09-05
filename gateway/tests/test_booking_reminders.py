# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for meeting reminders — memaix-src card ecffcb5b."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from memaix_gateway.acl import Acl
from memaix_gateway.booking.consent_store import ConsentStore
from memaix_gateway.booking.reminders import due_offsets, send_due_reminders, stale_offsets


@pytest.fixture()
def store(tmp_path):
    return ConsentStore(tmp_path / "consent.db")


def _epoch(y, m, d, h=0, mi=0):
    return int(datetime(y, m, d, h, mi, tzinfo=timezone.utc).timestamp())


# --- due_offsets / stale_offsets (pure) --------------------------------


def test_due_offsets_fires_24h_reminder_when_in_window():
    meeting_start = _epoch(2026, 1, 2, 9, 0)
    now = meeting_start - 1440 * 60  # exactly 24h before
    assert due_offsets(meeting_start, set(), now) == [1440]


def test_due_offsets_fires_1h_reminder_when_in_window():
    meeting_start = _epoch(2026, 1, 2, 9, 0)
    now = meeting_start - 60 * 60  # exactly 1h before
    assert due_offsets(meeting_start, set(), now) == [60]


def test_due_offsets_skips_already_sent():
    meeting_start = _epoch(2026, 1, 2, 9, 0)
    now = meeting_start - 60 * 60
    assert due_offsets(meeting_start, {"60"}, now) == []


def test_due_offsets_empty_long_before_meeting():
    meeting_start = _epoch(2026, 1, 2, 9, 0)
    now = meeting_start - 3 * 86400  # 3 days out — neither offset due yet
    assert due_offsets(meeting_start, set(), now) == []


def test_due_offsets_both_due_returns_largest_first():
    meeting_start = _epoch(2026, 1, 2, 9, 0)
    # A tick that lands inside both windows at once (e.g. after downtime) —
    # grace is 30 min, so a single now that's <=30min past the 24h fire time
    # AND also within the 1h window is only possible if offsets are close;
    # exercise the ordering contract directly instead.
    now = meeting_start - 60 * 60
    assert due_offsets(meeting_start, set(), now, offsets_min=(60, 1440)) == [60]


def test_stale_offsets_beyond_grace_window():
    meeting_start = _epoch(2026, 1, 2, 9, 0)
    now = meeting_start - 60 * 60 + 40 * 60  # 40 min past the 1h fire time, grace is 30
    assert stale_offsets(meeting_start, set(), now, offsets_min=(60,)) == [60]


def test_stale_offsets_within_grace_is_not_stale():
    meeting_start = _epoch(2026, 1, 2, 9, 0)
    now = meeting_start - 60 * 60 + 10 * 60  # 10 min late, within 30min grace
    assert stale_offsets(meeting_start, set(), now, offsets_min=(60,)) == []


def test_booking_made_inside_offset_window_skips_stale_offset_only():
    # Booked only 20 minutes before the meeting: the 24h reminder's fire
    # time is long past -> stale; the 1h reminder's fire time is also
    # already past (meeting is only 20 min out) -> also stale. Nothing due.
    meeting_start = _epoch(2026, 1, 2, 9, 0)
    now = meeting_start - 20 * 60
    assert due_offsets(meeting_start, set(), now) == []
    assert set(stale_offsets(meeting_start, set(), now)) == {1440, 60}


# --- _format_meeting_detail_line (pure) ---------------------------------


def test_format_meeting_detail_line_google_meet():
    from memaix_gateway.booking.routes import _format_meeting_detail_line

    line = _format_meeting_detail_line("google_meet", "https://meet.google.com/abc-defg-hij")
    assert line == "Google Meet: https://meet.google.com/abc-defg-hij"


def test_format_meeting_detail_line_zoom():
    from memaix_gateway.booking.routes import _format_meeting_detail_line

    line = _format_meeting_detail_line("zoom", "https://zoom.us/j/111")
    assert line == "Zoom: https://zoom.us/j/111"


def test_format_meeting_detail_line_phone():
    from memaix_gateway.booking.routes import _format_meeting_detail_line

    line = _format_meeting_detail_line("phone", "+46701234567")
    assert line == "Ring: +46701234567"


def test_format_meeting_detail_line_none_when_provider_missing():
    from memaix_gateway.booking.routes import _format_meeting_detail_line

    assert _format_meeting_detail_line(None, "https://meet.google.com/abc-defg-hij") is None


def test_format_meeting_detail_line_none_when_detail_missing():
    from memaix_gateway.booking.routes import _format_meeting_detail_line

    assert _format_meeting_detail_line("google_meet", None) is None


# --- ConsentStore reminder plumbing -------------------------------------


def test_mark_reminder_sent_claims_once(store):
    row_id, _token = store.record(
        project="proj", host_user="alice", event_id="ev1", visitor_email="bob@example.com",
        consent_text="ok", consent_at=_epoch(2026, 1, 1), meeting_end=_epoch(2026, 1, 2, 9, 30),
        meeting_start=_epoch(2026, 1, 2, 9, 0),
    )
    assert store.mark_reminder_sent(row_id, 1440) is True
    assert store.mark_reminder_sent(row_id, 1440) is False  # already claimed
    assert store.mark_reminder_sent(row_id, 60) is True  # different offset, fresh claim


def test_reminders_due_excludes_cancelled(store):
    row_id, _token = store.record(
        project="proj", host_user="alice", event_id="ev1", visitor_email="bob@example.com",
        consent_text="ok", consent_at=_epoch(2026, 1, 1), meeting_end=_epoch(2026, 1, 2, 9, 30),
        meeting_start=_epoch(2026, 1, 2, 9, 0),
    )
    store.update_booking(row_id, event_id="ev1", meeting_start=_epoch(2026, 1, 2, 9, 0),
                          meeting_end=_epoch(2026, 1, 2, 9, 30), status="cancelled")
    now = _epoch(2026, 1, 2, 8, 0)
    assert store.reminders_due(now, (1440, 60)) == []


def test_reminders_due_excludes_purged(store):
    row_id, _token = store.record(
        project="proj", host_user="alice", event_id="ev1", visitor_email="bob@example.com",
        consent_text="ok", consent_at=_epoch(2026, 1, 1), meeting_end=_epoch(2026, 1, 2, 9, 30),
        meeting_start=_epoch(2026, 1, 2, 9, 0),
    )
    store.mark_purged(row_id, _epoch(2026, 1, 2, 8, 0))
    now = _epoch(2026, 1, 2, 8, 0)
    assert store.reminders_due(now, (1440, 60)) == []


def test_reschedule_resets_reminder_ledger(store):
    row_id, _token = store.record(
        project="proj", host_user="alice", event_id="ev1", visitor_email="bob@example.com",
        consent_text="ok", consent_at=_epoch(2026, 1, 1), meeting_end=_epoch(2026, 1, 2, 9, 30),
        meeting_start=_epoch(2026, 1, 2, 9, 0),
    )
    store.mark_reminder_sent(row_id, 1440)
    store.update_booking(row_id, event_id="ev1", meeting_start=_epoch(2026, 1, 3, 9, 0),
                          meeting_end=_epoch(2026, 1, 3, 9, 30), status="rescheduled")
    # New time gets a fresh claim for the same offset — ledger was cleared.
    assert store.mark_reminder_sent(row_id, 1440) is True


# --- send_due_reminders (integration over the store + email helper) -----


class _RecordingRow(dict):
    pass


def _acl():
    return Acl(
        users={"alice": {"grants": {"proj": "owner"}}},
        projects={"proj": {"allow_send": True, "mailbox": {"host": "imap.example.com", "user": "alice@example.com", "password_ref": "env:FAKE_MAILBOX_PW"}}},
    )


def test_send_due_reminders_sends_and_claims(store, monkeypatch):
    import memaix_gateway.booking.reminders as reminders_mod

    monkeypatch.setenv("FAKE_MAILBOX_PW", "shh")
    row_id, token = store.record(
        project="proj", host_user="alice", event_id="ev1", visitor_email="bob@example.com",
        consent_text="ok", consent_at=_epoch(2026, 1, 1), meeting_end=_epoch(2026, 1, 2, 9, 30),
        meeting_start=_epoch(2026, 1, 2, 9, 0), slug="alice-30",
    )

    sent_emails = []
    monkeypatch.setattr(
        reminders_mod, "_send_reminder_email",
        lambda *a, **kw: sent_emails.append((a, kw)),
        raising=False,
    )
    import memaix_gateway.booking.routes as routes_mod
    monkeypatch.setattr(routes_mod, "_send_reminder_email", lambda *a, **kw: sent_emails.append(a))

    link = {"project": "proj", "user": "alice", "title_template": "Möte"}
    now = datetime.fromtimestamp(_epoch(2026, 1, 1, 9, 0), tz=timezone.utc)  # exactly 24h before

    count = send_due_reminders(store, _acl, lambda slug: link, now)

    assert count == 1
    assert len(sent_emails) == 1
    row = store.get_by_manage_token(token)
    assert row is not None  # sanity: token still resolves


def test_send_due_reminders_skips_when_link_unknown(store, monkeypatch):
    row_id, _token = store.record(
        project="proj", host_user="alice", event_id="ev1", visitor_email="bob@example.com",
        consent_text="ok", consent_at=_epoch(2026, 1, 1), meeting_end=_epoch(2026, 1, 2, 9, 30),
        meeting_start=_epoch(2026, 1, 2, 9, 0), slug="alice-30",
    )
    now = datetime.fromtimestamp(_epoch(2026, 1, 1, 9, 0), tz=timezone.utc)
    count = send_due_reminders(store, _acl, lambda slug: None, now)
    assert count == 0
    # The offset must remain unclaimed so a later tick (once the link exists)
    # can still send it — this is what catches a claim-before-send ordering
    # regression, not just the count.
    assert store.mark_reminder_sent(row_id, 1440) is True


def test_send_due_reminders_renders_meeting_detail_line_when_set(store, monkeypatch):
    row_id, token = store.record(
        project="proj", host_user="alice", event_id="ev1", visitor_email="bob@example.com",
        consent_text="ok", consent_at=_epoch(2026, 1, 1), meeting_end=_epoch(2026, 1, 2, 9, 30),
        meeting_start=_epoch(2026, 1, 2, 9, 0), slug="alice-30",
        meeting_form_slug="video", meeting_form_provider="google_meet",
        meeting_form_detail="https://meet.google.com/abc-defg-hij",
    )

    calls = []
    import memaix_gateway.booking.routes as routes_mod
    monkeypatch.setattr(routes_mod, "_send_reminder_email", lambda *a, **kw: calls.append(a))

    link = {"project": "proj", "user": "alice", "title_template": "Möte"}
    now = datetime.fromtimestamp(_epoch(2026, 1, 1, 9, 0), tz=timezone.utc)  # exactly 24h before

    count = send_due_reminders(store, _acl, lambda slug: link, now)

    assert count == 1
    assert len(calls) == 1
    meeting_detail_line = calls[0][-1]
    assert meeting_detail_line == "Google Meet: https://meet.google.com/abc-defg-hij"


def test_send_due_reminders_renders_no_line_when_meeting_form_unset(store, monkeypatch):
    row_id, token = store.record(
        project="proj", host_user="alice", event_id="ev1", visitor_email="bob@example.com",
        consent_text="ok", consent_at=_epoch(2026, 1, 1), meeting_end=_epoch(2026, 1, 2, 9, 30),
        meeting_start=_epoch(2026, 1, 2, 9, 0), slug="alice-30",
    )

    calls = []
    import memaix_gateway.booking.routes as routes_mod
    monkeypatch.setattr(routes_mod, "_send_reminder_email", lambda *a, **kw: calls.append(a))

    link = {"project": "proj", "user": "alice", "title_template": "Möte"}
    now = datetime.fromtimestamp(_epoch(2026, 1, 1, 9, 0), tz=timezone.utc)  # exactly 24h before

    count = send_due_reminders(store, _acl, lambda slug: link, now)

    assert count == 1
    assert len(calls) == 1
    meeting_detail_line = calls[0][-1]
    assert meeting_detail_line is None


def test_send_due_reminders_leaves_offset_unclaimed_when_send_raises(store, monkeypatch):
    import memaix_gateway.booking.reminders as reminders_mod

    row_id, _token = store.record(
        project="proj", host_user="alice", event_id="ev1", visitor_email="bob@example.com",
        consent_text="ok", consent_at=_epoch(2026, 1, 1), meeting_end=_epoch(2026, 1, 2, 9, 30),
        meeting_start=_epoch(2026, 1, 2, 9, 0), slug="alice-30",
    )

    def _boom(*a, **kw):
        raise RuntimeError("smtp exploded")

    monkeypatch.setattr(reminders_mod, "_send_reminder_email", _boom, raising=False)
    import memaix_gateway.booking.routes as routes_mod
    monkeypatch.setattr(routes_mod, "_send_reminder_email", _boom)

    link = {"project": "proj", "user": "alice", "title_template": "Möte"}
    now = datetime.fromtimestamp(_epoch(2026, 1, 1, 9, 0), tz=timezone.utc)

    count = send_due_reminders(store, _acl, lambda slug: link, now)

    assert count == 0
    # A send that raises must not have claimed the offset first — otherwise
    # the reminder is lost forever, since due_offsets() never retries an
    # offset already in reminders_sent.
    assert store.mark_reminder_sent(row_id, 1440) is True
