# SPDX-License-Identifier: AGPL-3.0-or-later
"""(subject, client_id) approval store — the real fix for memaix-src 4c8f32fe.

Hydra's own "remember me" is scoped to the BROWSER (a cookie on the login
challenge flow), not to (identity, OAuth client). That let a second client
logging in as a different user in the same browser silently inherit the
first client's already-authenticated identity — Hydra's admin API reported
`skip: true` regardless of which client was asking.

This store lets login-app make that decision itself: `is_approved(subject,
client_id)` says whether *this* client has already had *this* subject log in
through the password form. login_get only honours Hydra's `skip` when this
store also agrees; a brand new client always sees the login form even if
Hydra's browser-scoped session would have skipped it.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

_DB_PATH = os.environ.get("MEMAIX_APPROVED_CLIENTS_DB", "/data/approved_clients.db")


def _connect(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS approved_clients ("
        "subject TEXT NOT NULL, client_id TEXT NOT NULL, "
        "approved_at TEXT NOT NULL DEFAULT (datetime('now')), "
        "PRIMARY KEY (subject, client_id))"
    )
    return conn


def is_approved(subject: str, client_id: str, *, db_path: str = _DB_PATH) -> bool:
    if not subject or not client_id:
        # An empty client_id would let two different clients that both fail
        # to report one share a single "" row — the exact leak this store
        # exists to prevent. Hydra always sets client_id in practice, but
        # never trust a missing value as approval.
        return False
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM approved_clients WHERE subject = ? AND client_id = ?",
            (subject, client_id),
        ).fetchone()
        return row is not None


def approve(subject: str, client_id: str, *, db_path: str = _DB_PATH) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO approved_clients (subject, client_id) VALUES (?, ?)",
            (subject, client_id),
        )
        conn.commit()
