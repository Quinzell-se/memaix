# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E harness: a real gateway web-UI served by uvicorn + real Chromium.

Not collected by the default unit run (pyproject testpaths = ["tests"]).
Run with:  python -m pytest -q tests_e2e

Environment is prepared at MODULE IMPORT TIME, before any memaix_gateway
import — several modules (config.CONFIG_DIR, board auth) read env when first
imported, so ordering matters. The whole stack runs in-process (uvicorn in a
thread), which also lets tests monkeypatch server-side dispatch tables.

Browser resolution: try the Playwright registry first (CI runs
`playwright install chromium`); fall back to the container's pre-provisioned
/opt/pw-browsers/chromium (version-pinned installs must not re-download).
"""

from __future__ import annotations

import atexit
import hashlib
import os
import shutil
import socket
import tempfile
import threading
from pathlib import Path

# ---------------------------------------------------------------------------
# Environment BEFORE any memaix_gateway import
# ---------------------------------------------------------------------------

_E2E_ROOT = Path(tempfile.mkdtemp(prefix="memaix-e2e-"))
atexit.register(shutil.rmtree, _E2E_ROOT, ignore_errors=True)

_CONFIG_DIR = _E2E_ROOT / "config"
_VAULT = _E2E_ROOT / "vault"
_CONFIG_DIR.mkdir(parents=True)
_VAULT.mkdir(parents=True)

E2E_SECRET = "e2e-system-secret-0123456789abcdef"
ALICE_PASSWORD = "alice-e2e-password"


def _pbkdf2(password: str) -> str:
    salt = b"\x11" * 16
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return f"{salt.hex()}:{derived.hex()}"


os.environ["MEMAIX_CONFIG_DIR"] = str(_CONFIG_DIR)
os.environ["HYDRA_SYSTEM_SECRET"] = E2E_SECRET
os.environ["MEMAIX_ALLOWED_USERS"] = "alice,bob"
os.environ["MEMAIX_LOGIN_PASSWORD_HASH_ALICE"] = _pbkdf2(ALICE_PASSWORD)
os.environ["MEMAIX_OUTBOX_DB"] = str(_E2E_ROOT / "outbox.db")
os.environ["MEMAIX_AUDIT_DB"] = str(_E2E_ROOT / "audit.db")
os.environ["MEMAIX_ACTIONS_DB"] = str(_E2E_ROOT / "actions.db")
os.environ["MEMAIX_NOTIFY_DB"] = str(_E2E_ROOT / "notify.db")
os.environ["MEMAIX_INDEX_DB"] = str(_E2E_ROOT / "index.db")
os.environ["MEMAIX_SECRETS_DIR"] = str(_E2E_ROOT / "secrets")
os.environ["MEMAIX_ALLOW_EPHEMERAL_KEY"] = "1"  # no real OAuth tokens in e2e

_CONFIG_DIR.joinpath("acl.yaml").write_text(
    f"""users:
  alice:
    admin: true
    grants:
      demo: owner
  bob:
    grants:
      demo: reader
projects:
  demo:
    vault: {_VAULT}
    allow_send: true
    outbox: review
""",
    encoding="utf-8",
)
_CONFIG_DIR.joinpath("memaix.yaml").write_text(
    "memaix:\n  server:\n    locale: en\n", encoding="utf-8"
)
_CONFIG_DIR.joinpath("brand.yaml").write_text("name: memaix\n", encoding="utf-8")

# ---------------------------------------------------------------------------
# Now the gateway can be imported
# ---------------------------------------------------------------------------

import pytest  # noqa: E402
import uvicorn  # noqa: E402
from starlette.applications import Starlette  # noqa: E402

from memaix_gateway.acl import Acl  # noqa: E402
from memaix_gateway.backends.memory_store import MemoryStore  # noqa: E402
from memaix_gateway.board.routes import _make_cookie, board_routes  # noqa: E402
from memaix_gateway.tools.memory import memory_write  # noqa: E402
from memaix_gateway.web.routes import web_routes  # noqa: E402

BASE_HOST = "127.0.0.1"


def _seed_vault() -> None:
    """A couple of notes so the memory explorer has something to show."""
    MemoryStore._clear_instances()
    acl = Acl(
        users={"alice": {"grants": {"demo": "owner"}}},
        projects={"demo": {"vault": str(_VAULT)}},
    )
    memory_write(acl, "alice", "demo", "welcome.md", "# Welcome\n\nFirst **e2e** note.")
    memory_write(acl, "alice", "demo", "ideas/zebra.md", "A unique zebra idea.")
    memory_write(acl, "alice", "demo", "welcome.md", "# Welcome\n\nSecond revision.")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind((BASE_HOST, 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def base_url() -> str:
    _seed_vault()
    app = Starlette(routes=[*board_routes, *web_routes])
    port = _free_port()
    config = uvicorn.Config(app, host=BASE_HOST, port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    import time

    for _ in range(200):
        if server.started:
            break
        time.sleep(0.05)
    else:
        raise RuntimeError("uvicorn did not start")
    yield f"http://{BASE_HOST}:{port}"
    server.should_exit = True
    thread.join(timeout=5)


# ---------------------------------------------------------------------------
# Browser fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception:
            b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium")
        yield b
        b.close()


@pytest.fixture()
def context(browser, base_url):
    ctx = browser.new_context(base_url=base_url)
    yield ctx
    ctx.close()


@pytest.fixture()
def page(context):
    page = context.new_page()
    # Fail tests on JS errors — silent frontend breakage must not pass.
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    yield page
    assert errors == [], f"JS errors on page: {errors}"


def login_as(context, user: str) -> None:
    """Inject a valid signed board-session cookie (computed in-process with the
    same secret the server uses) — deterministic, no UI login round-trip."""
    context.add_cookies(
        [{
            "name": "memaix_board",
            "value": _make_cookie(user),
            "domain": BASE_HOST,
            "path": "/",
        }]
    )


@pytest.fixture()
def alice_page(context, page):
    login_as(context, "alice")
    return page


@pytest.fixture()
def bob_page(context, page):
    login_as(context, "bob")
    return page
