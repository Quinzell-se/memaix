# SPDX-License-Identifier: AGPL-3.0-or-later
"""Encrypted per-user OAuth token store backed by SQLite.

Master key is supplied externally (env: TOKEN_MASTER_KEY).
Fernet provides AES-128-CBC + HMAC-SHA256 authenticated encryption.
Thread-safe via a single Lock per instance.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet


class TokenStore:
    """One instance per deployment — shared across all projects."""

    def __init__(self, db_path: Path, fernet: Fernet) -> None:
        self._path = db_path
        self._fernet = fernet
        self._lock = threading.Lock()
        self._init_db()

    @classmethod
    def for_path(cls, db_path: Path, master_key: bytes) -> "TokenStore":
        fernet = Fernet(master_key)
        return cls(db_path, fernet)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_tokens (
                        id            INTEGER PRIMARY KEY AUTOINCREMENT,
                        memaix_user   TEXT NOT NULL,
                        provider      TEXT NOT NULL,
                        account_email TEXT NOT NULL,
                        encrypted_data BLOB NOT NULL,
                        status        TEXT NOT NULL DEFAULT 'active',
                        updated_at    TEXT NOT NULL,
                        UNIQUE(memaix_user, provider, account_email)
                    )
                    """
                )
                conn.commit()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def store(self, user: str, provider: str, account: str, token_data: dict) -> None:
        """Encrypt and store (or overwrite) token_data. Status is set to 'active'."""
        blob = self._fernet.encrypt(json.dumps(token_data).encode())
        now = self._now()
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO user_tokens
                        (memaix_user, provider, account_email, encrypted_data, status, updated_at)
                    VALUES (?, ?, ?, ?, 'active', ?)
                    ON CONFLICT(memaix_user, provider, account_email)
                    DO UPDATE SET
                        encrypted_data = excluded.encrypted_data,
                        status         = 'active',
                        updated_at     = excluded.updated_at
                    """,
                    (user, provider, account, blob, now),
                )
                conn.commit()

    def load_one(self, user: str, provider: str, account: str) -> dict | None:
        """Decrypt and return token_data, or None if not found."""
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT encrypted_data FROM user_tokens
                    WHERE memaix_user=? AND provider=? AND account_email=?
                    """,
                    (user, provider, account),
                ).fetchone()
        if row is None:
            return None
        return json.loads(self._fernet.decrypt(bytes(row["encrypted_data"])))

    def list_accounts(self, user: str) -> list[dict]:
        """Return [{provider, account, status, scopes}] for all linked accounts."""
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT provider, account_email, encrypted_data, status
                    FROM user_tokens
                    WHERE memaix_user=?
                    ORDER BY provider, account_email
                    """,
                    (user,),
                ).fetchall()
        result = []
        for row in rows:
            token_data = json.loads(self._fernet.decrypt(bytes(row["encrypted_data"])))
            result.append(
                {
                    "provider": row["provider"],
                    "account": row["account_email"],
                    "status": row["status"],
                    "scopes": token_data.get("scope", "").split()
                    if token_data.get("scope")
                    else [],
                }
            )
        return result

    def delete(self, user: str, provider: str, account: str) -> bool:
        """Delete token. Returns True if found and deleted."""
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute(
                    """
                    DELETE FROM user_tokens
                    WHERE memaix_user=? AND provider=? AND account_email=?
                    """,
                    (user, provider, account),
                )
                conn.commit()
                return cur.rowcount > 0

    def mark_needs_relink(self, user: str, provider: str, account: str) -> None:
        """Set status='needs_relink' for this account."""
        now = self._now()
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE user_tokens SET status='needs_relink', updated_at=?
                    WHERE memaix_user=? AND provider=? AND account_email=?
                    """,
                    (now, user, provider, account),
                )
                conn.commit()
