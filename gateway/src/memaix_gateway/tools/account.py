# SPDX-License-Identifier: AGPL-3.0-or-later
"""account_* tools — OAuth account linking/unlinking.

In-process state for pending OAuth flows is stored in _pending_states.
This is intentionally simple: the gateway is single-process and states
expire after 10 minutes.  Clear _pending_states in tests via monkeypatch
or by calling _pending_states.clear() in teardown.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from ..acl import Acl

if TYPE_CHECKING:
    from ..backends.token_store import TokenStore

# In-process state for pending OAuth flows: state_token → {user_id, provider, exp}
# This is the default (memory) backend. For multi-worker deployments set
# MEMAIX_STATE_DB to persist pending states in SQLite so the callback can be
# handled by a different worker than the one that started the flow.
_pending_states: dict[str, dict] = {}

PROVIDERS = {"google", "microsoft"}


class _PendingStateSQLite:
    """SQLite-backed pending-state store shared across processes."""

    def __init__(self, db_path: Path) -> None:
        self._path = db_path
        self._lock = threading.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS oauth_pending "
                "(state TEXT PRIMARY KEY, user_id TEXT NOT NULL, "
                " provider TEXT NOT NULL, exp INTEGER NOT NULL)"
            )
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def put(self, state: str, data: dict) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO oauth_pending (state, user_id, provider, exp) "
                "VALUES (?, ?, ?, ?)",
                (state, data["user_id"], data["provider"], int(data["exp"])),
            )
            conn.commit()

    def pop(self, state: str) -> dict | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT user_id, provider, exp FROM oauth_pending WHERE state=?", (state,)
            ).fetchone()
            if row is None:
                return None
            conn.execute("DELETE FROM oauth_pending WHERE state=?", (state,))
            conn.commit()
        return {"user_id": row["user_id"], "provider": row["provider"], "exp": row["exp"]}

    def purge(self, now: int) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM oauth_pending WHERE exp < ?", (now,))
            conn.commit()


_sqlite_store: _PendingStateSQLite | None = None


def _get_state_store() -> _PendingStateSQLite | None:
    """Return the SQLite store if MEMAIX_STATE_DB is set, else None (memory)."""
    global _sqlite_store
    db = os.environ.get("MEMAIX_STATE_DB")
    if not db:
        return None
    if _sqlite_store is None:
        _sqlite_store = _PendingStateSQLite(Path(db))
    return _sqlite_store


def _put_state(state: str, data: dict) -> None:
    store = _get_state_store()
    if store is not None:
        store.put(state, data)
    else:
        _pending_states[state] = data


def _pop_state(state: str) -> dict | None:
    store = _get_state_store()
    if store is not None:
        return store.pop(state)
    return _pending_states.pop(state, None)


def _purge_expired(now: int) -> None:
    store = _get_state_store()
    if store is not None:
        store.purge(now)
        return
    for k in [k for k, v in list(_pending_states.items()) if v["exp"] < now]:
        del _pending_states[k]


def account_link(acl: Acl, user_id: str, provider: str, public_url: str) -> dict:
    """Generate an OAuth link URL. Returns {link_url, expires_in, provider}."""
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider: {provider!r}")

    import secrets
    import time

    state = secrets.token_urlsafe(32)
    exp = int(time.time()) + 600
    _put_state(state, {"user_id": user_id, "provider": provider, "exp": exp})

    # Clean up expired states while we're here.
    _purge_expired(int(time.time()))

    link_url = f"{public_url.rstrip('/')}/link/{provider}?state={state}"
    return {"link_url": link_url, "expires_in": 600, "provider": provider}


def account_list(acl: Acl, user_id: str, store: TokenStore) -> list[dict]:
    """List linked accounts for the calling user."""
    return store.list_accounts(user_id)


def account_unlink(
    acl: Acl,
    user_id: str,
    provider: str,
    account: str,
    store: TokenStore,
) -> dict:
    """Unlink (delete) an account. Returns {ok: True}."""
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider: {provider!r}")
    deleted = store.delete(user_id, provider, account)
    if not deleted:
        raise FileNotFoundError(f"no linked account: {provider}/{account}")
    return {"ok": True}


def validate_state(state: str) -> dict | None:
    """Validate an OAuth state parameter. Returns the pending dict or None if invalid/expired."""
    import time

    pending = _pop_state(state)
    if pending and pending["exp"] >= int(time.time()):
        return pending
    return None
