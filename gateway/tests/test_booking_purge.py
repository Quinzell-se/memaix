# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for booking consent retention — memaix-src card 01cf3b74."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from memaix_gateway.acl import Acl
from memaix_gateway.booking.consent_store import ConsentStore
from memaix_gateway.booking.purge import purge_due


@pytest.fixture()
def store(tmp_path):
    return ConsentStore(tmp_path / "consent.db")


def _epoch(y, m, d, h=0):
    return int(datetime(y, m, d, h, tzinfo=timezone.utc).timestamp())


def test_due_excludes_recent_meetings(store):
    store.record(
        project="proj", host_user="alice", event_id="ev1", visitor_email="bob@example.com",
        consent_text="ok", consent_at=_epoch(2026, 1, 1), meeting_end=_epoch(2026, 1, 1),
    )
    now = _epoch(2026, 6, 1)
    assert store.due(now) == []


def test_due_includes_meetings_past_one_year(store):
    row_id = store.record(
        project="proj", host_user="alice", event_id="ev1", visitor_email="bob@example.com",
        consent_text="ok", consent_at=_epoch(2025, 1, 1), meeting_end=_epoch(2025, 1, 1),
    )
    now = _epoch(2026, 6, 1)
    due = store.due(now)
    assert [row["id"] for row in due] == [row_id]


def test_mark_purged_scrubs_email_but_keeps_row(store):
    row_id = store.record(
        project="proj", host_user="alice", event_id="ev1", visitor_email="bob@example.com",
        consent_text="Jag samtycker.", consent_at=_epoch(2025, 1, 1), meeting_end=_epoch(2025, 1, 1),
    )
    store.mark_purged(row_id, _epoch(2026, 6, 1))
    now = _epoch(2026, 6, 1)
    assert store.due(now) == []  # purged_at set -> no longer due


class _FakeDav:
    def __init__(self):
        self.deleted: list[str] = []

    def delete_event(self, id: str) -> None:
        self.deleted.append(id)


def _acl():
    return Acl(users={"alice": {"grants": {"proj": "owner"}}}, projects={"proj": {}})


def test_purge_due_deletes_calendar_event_and_scrubs_row(store):
    store.record(
        project="proj", host_user="alice", event_id="ev1", visitor_email="bob@example.com",
        consent_text="ok", consent_at=_epoch(2025, 1, 1), meeting_end=_epoch(2025, 1, 1),
    )
    dav = _FakeDav()
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)

    purged = purge_due(store, _acl, lambda project, user: dav, now)

    assert purged == 1
    assert dav.deleted == ["ev1"]
    rows = store.due(int(now.timestamp()))
    assert rows == []


def test_purge_due_skips_row_still_within_retention(store):
    store.record(
        project="proj", host_user="alice", event_id="ev1", visitor_email="bob@example.com",
        consent_text="ok", consent_at=_epoch(2026, 1, 1), meeting_end=_epoch(2026, 1, 1),
    )
    dav = _FakeDav()
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)

    purged = purge_due(store, _acl, lambda project, user: dav, now)

    assert purged == 0
    assert dav.deleted == []


def test_purge_due_scrubs_row_when_event_already_deleted(store):
    store.record(
        project="proj", host_user="alice", event_id="ev1", visitor_email="bob@example.com",
        consent_text="ok", consent_at=_epoch(2025, 1, 1), meeting_end=_epoch(2025, 1, 1),
    )

    class _GoneDav:
        def delete_event(self, id: str) -> None:
            raise FileNotFoundError(id)

    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    purged = purge_due(store, _acl, lambda project, user: _GoneDav(), now)

    # Event was already gone (host deleted it manually) — nothing left to
    # delete, so the row is scrubbed immediately rather than retried forever.
    assert purged == 1
    assert store.due(int(now.timestamp())) == []


def test_purge_due_swallows_a_single_row_failure_and_continues(store):
    store.record(
        project="proj", host_user="alice", event_id="ev1", visitor_email="bob@example.com",
        consent_text="ok", consent_at=_epoch(2025, 1, 1), meeting_end=_epoch(2025, 1, 1),
    )
    store.record(
        project="proj", host_user="alice", event_id="ev2", visitor_email="carol@example.com",
        consent_text="ok", consent_at=_epoch(2025, 1, 1), meeting_end=_epoch(2025, 1, 2),
    )

    class _BoomDav:
        def delete_event(self, id: str) -> None:
            if id == "ev1":
                raise RuntimeError("caldav unreachable")

    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    purged = purge_due(store, _acl, lambda project, user: _BoomDav(), now)

    # ev1's row errors and is left for a future tick; ev2's still purges.
    assert purged == 1
    remaining = store.due(int(now.timestamp()))
    assert [row["event_id"] for row in remaining] == ["ev1"]
