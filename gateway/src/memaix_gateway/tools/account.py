# SPDX-License-Identifier: AGPL-3.0-or-later
"""account_* tools — OAuth account linking/unlinking.

In-process state for pending OAuth flows is stored in _pending_states.
This is intentionally simple: the gateway is single-process and states
expire after 10 minutes.  Clear _pending_states in tests via monkeypatch
or by calling _pending_states.clear() in teardown.
"""

from __future__ import annotations

from ..acl import Acl

# In-process state for pending OAuth flows: state_token → {user_id, provider, exp}
_pending_states: dict[str, dict] = {}

PROVIDERS = {"google", "microsoft"}


def account_link(acl: Acl, user_id: str, provider: str, public_url: str) -> dict:
    """Generate an OAuth link URL. Returns {link_url, expires_in, provider}."""
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider: {provider!r}")

    import secrets
    import time

    state = secrets.token_urlsafe(32)
    exp = int(time.time()) + 600
    _pending_states[state] = {"user_id": user_id, "provider": provider, "exp": exp}

    # Clean up expired states while we're here.
    now = int(time.time())
    expired = [k for k, v in list(_pending_states.items()) if v["exp"] < now]
    for k in expired:
        del _pending_states[k]

    link_url = f"{public_url.rstrip('/')}/link/{provider}?state={state}"
    return {"link_url": link_url, "expires_in": 600, "provider": provider}


def account_list(acl: Acl, user_id: str, store: "TokenStore") -> list[dict]:  # noqa: F821
    """List linked accounts for the calling user."""
    return store.list_accounts(user_id)


def account_unlink(
    acl: Acl,
    user_id: str,
    provider: str,
    account: str,
    store: "TokenStore",  # noqa: F821
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

    pending = _pending_states.pop(state, None)
    if pending and pending["exp"] >= int(time.time()):
        return pending
    return None
