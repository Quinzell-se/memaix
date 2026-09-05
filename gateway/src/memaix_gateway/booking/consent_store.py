# SPDX-License-Identifier: AGPL-3.0-or-later
"""GDPR consent log for public bookings — memaix-src card 01cf3b74.

booking_create writes no local record of a booking anywhere — the visitor's
PII (name, purpose, email as attendee) lives only on the calendar event
itself. That's a problem twice over: there is nothing to prove *that* and
*when* a visitor consented, and there is no reliable way to tell a booking
event apart from any other event on the host's calendar once it's time to
purge it. This store is the one place that solves both: it records consent
alongside the calendar event's id and the meeting's end time, so purge.py
can find events that are actually bookings and are actually old enough,
without ever having to guess from calendar content.

Mirrors _PendingStateSQLite (tools/account.py) and ActionQueue
(outbox/queue.py): SQLite, WAL mode, one threading.Lock, a fresh connection
per operation. Same conventions as everything else that needs
process/restart-durable local state in this gateway.
"""

from __future__ import annotations

import os
import secrets
import sqlite3
import threading
import uuid
from pathlib import Path

_DEFAULT_DB_PATH = "/tmp/memaix-consent.db"
RETENTION_DAYS = 365


class ConsentStore:
    """SQLite-backed log of booking consent, keyed by an internal row id
    (not the calendar event id, which purge.py deletes and which a
    Google/CalDAV adapter may not have even generated at record() time)."""

    def __init__(self, db_path: Path) -> None:
        self._path = db_path
        self._lock = threading.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS booking_consent (
                    id            TEXT PRIMARY KEY,
                    project       TEXT NOT NULL,
                    host_user     TEXT NOT NULL,
                    event_id      TEXT,
                    visitor_email TEXT,
                    consent_text  TEXT NOT NULL,
                    consent_at    INTEGER NOT NULL,
                    meeting_end   INTEGER NOT NULL,
                    purged_at     INTEGER
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_consent_due "
                "ON booking_consent(meeting_end) WHERE purged_at IS NULL"
            )
            # Additive migration for card 8056150d (reschedule/cancel).
            # SQLite has no "ADD COLUMN IF NOT EXISTS" — probe and ignore
            # the OperationalError on a database that already has them.
            for ddl in (
                "ALTER TABLE booking_consent ADD COLUMN slug TEXT",
                "ALTER TABLE booking_consent ADD COLUMN manage_token TEXT",
                "ALTER TABLE booking_consent ADD COLUMN status TEXT NOT NULL DEFAULT 'confirmed'",
            ):
                try:
                    conn.execute(ddl)
                except sqlite3.OperationalError:
                    pass
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_consent_manage_token "
                "ON booking_consent(manage_token) WHERE manage_token IS NOT NULL"
            )
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def record(
        self,
        *,
        project: str,
        host_user: str,
        event_id: str | None,
        visitor_email: str,
        consent_text: str,
        consent_at: int,
        meeting_end: int,
        slug: str | None = None,
    ) -> tuple[str, str]:
        """Returns (row_id, manage_token). manage_token is the capability a
        booker or host later presents to /booking/{token}/... to reschedule
        or cancel this booking — see card 8056150d."""
        row_id = uuid.uuid4().hex
        manage_token = secrets.token_urlsafe(32)
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO booking_consent "
                "(id, project, host_user, event_id, visitor_email, consent_text, "
                " consent_at, meeting_end, purged_at, slug, manage_token, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, 'confirmed')",
                (row_id, project, host_user, event_id, visitor_email, consent_text,
                 consent_at, meeting_end, slug, manage_token),
            )
            conn.commit()
        return row_id, manage_token

    def get_by_manage_token(self, manage_token: str) -> dict | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT id, project, host_user, event_id, visitor_email, slug, status, meeting_end "
                "FROM booking_consent WHERE manage_token = ?",
                (manage_token,),
            ).fetchone()
        return dict(row) if row else None

    def update_booking(self, row_id: str, *, event_id: str | None, meeting_end: int, status: str) -> None:
        """Reschedule moves meeting_end (purge.py's due() keys off it) and
        may keep the same event_id (an in-place calendar_update) or a new
        one; cancel just flips status so a cancelled booking can't be
        rescheduled later."""
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE booking_consent SET event_id = ?, meeting_end = ?, status = ? WHERE id = ?",
                (event_id, meeting_end, status, row_id),
            )
            conn.commit()

    def due(self, now_epoch: int, retention_days: int = RETENTION_DAYS) -> list[dict]:
        """Rows whose meeting ended more than *retention_days* ago and
        haven't been purged yet."""
        cutoff = now_epoch - retention_days * 86400
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT id, project, host_user, event_id, visitor_email "
                "FROM booking_consent WHERE meeting_end < ? AND purged_at IS NULL",
                (cutoff,),
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_purged(self, row_id: str, when: int) -> None:
        """Nulls the visitor's email (the only PII this store ever holds)
        and stamps purged_at. The row itself stays — consent_text,
        consent_at and meeting_end remain as proof consent existed and was
        honored, without retaining the data that made it identifying."""
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE booking_consent SET visitor_email = NULL, purged_at = ? WHERE id = ?",
                (when, row_id),
            )
            conn.commit()


_store: ConsentStore | None = None


def get_consent_store() -> ConsentStore:
    global _store
    if _store is None:
        db_path = Path(os.environ.get("MEMAIX_CONSENT_DB", _DEFAULT_DB_PATH))
        _store = ConsentStore(db_path)
    return _store
