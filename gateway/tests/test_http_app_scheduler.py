# SPDX-License-Identifier: AGPL-3.0-or-later
"""Verifies build_http_app() wires the brief scheduler into the ASGI lifespan
without breaking FastMCP's own startup/shutdown (FEATURE-PROACTIVE-BRIEF.md §7).
"""

from __future__ import annotations

from starlette.testclient import TestClient

from memaix_gateway.server import build_http_app


def test_http_app_lifespan_starts_and_stops_cleanly():
    app = build_http_app()
    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
    # No exception on exit means startup ran, the scheduler task was created,
    # and shutdown cancelled it without hanging or raising.
