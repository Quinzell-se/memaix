# SPDX-License-Identifier: AGPL-3.0-or-later
"""Smoke tests for the server-layer tool wrappers (_tool_call).

Drives tools through the FastMCP-registered functions in stdio mode
(MEMAIX_USER) to verify the shared identity + rate-limit + ACL + audit path.
"""

from __future__ import annotations

import time

import pytest

from memaix_gateway import server
from memaix_gateway.acl import AccessDenied, Acl
from memaix_gateway.safety.audit import AuditLog


@pytest.fixture()
def wired(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    (vault / "backlog").mkdir(parents=True)
    acl = Acl(
        users={
            "alice": {"grants": {"proj": "owner"}},
            "bob": {"grants": {"proj": "reader"}},
        },
        projects={"proj": {"vault": str(vault)}},
    )
    AuditLog._clear_instances()
    monkeypatch.setattr(server, "_acl", acl)
    monkeypatch.setattr(server, "_audit", AuditLog.for_path(tmp_path / "audit.db"))
    monkeypatch.setenv("MEMAIX_USER", "alice")
    server._rate_limiter._windows.clear()
    return vault, acl


def test_files_roundtrip_via_server(wired):
    server.files_write("proj", "/notes.txt", "hello")
    assert server.files_read("proj", "/notes.txt") == "hello"


def test_backlog_via_server_records_audit(wired):
    r = server.backlog_add("proj", "Title", "Body")
    assert server.backlog_get("proj", r["id"])["title"] == "Title"
    tools = [e["tool"] for e in server._get_audit().tail(20)]
    assert "backlog_add" in tools and "backlog_get" in tools


def test_server_enforces_acl(wired, monkeypatch):
    # bob is only a reader; files_read requires collaborator.
    monkeypatch.setenv("MEMAIX_USER", "bob")
    with pytest.raises(AccessDenied):
        server.files_read("proj", "/notes.txt")


def test_server_enforces_rate_limit(wired):
    # Fill the user's window so the next call is denied.
    server._rate_limiter._inject_timestamps("user:alice", [time.monotonic()] * 60)
    with pytest.raises(RuntimeError, match="rate_limited"):
        server.memory_search("proj", "anything")


def test_failed_tool_call_is_audited(wired):
    with pytest.raises(Exception):
        server.backlog_get("proj", "../../escape")  # blocked by path validation
    last = server._get_audit().tail(5)
    assert any(e["tool"] == "backlog_get" and e["ok"] is False for e in last)


# ------------------------------------------------------------------
# TOKEN_MASTER_KEY hardening
# ------------------------------------------------------------------


def test_http_mode_requires_master_key(monkeypatch):
    monkeypatch.setattr(server, "_token_store", None)
    monkeypatch.delenv("TOKEN_MASTER_KEY", raising=False)
    monkeypatch.delenv("MEMAIX_ALLOW_EPHEMERAL_KEY", raising=False)
    monkeypatch.setenv("MEMAIX_TRANSPORT", "http")
    with pytest.raises(RuntimeError, match="TOKEN_MASTER_KEY"):
        server._get_token_store()


def test_http_mode_ephemeral_opt_in(monkeypatch):
    monkeypatch.setattr(server, "_token_store", None)
    monkeypatch.delenv("TOKEN_MASTER_KEY", raising=False)
    monkeypatch.setenv("MEMAIX_TRANSPORT", "http")
    monkeypatch.setenv("MEMAIX_ALLOW_EPHEMERAL_KEY", "1")
    with pytest.warns(RuntimeWarning):
        store = server._get_token_store()
    assert store is not None


def test_stdio_mode_allows_ephemeral_key(monkeypatch):
    monkeypatch.setattr(server, "_token_store", None)
    monkeypatch.delenv("TOKEN_MASTER_KEY", raising=False)
    monkeypatch.delenv("MEMAIX_TRANSPORT", raising=False)
    monkeypatch.delenv("MEMAIX_ALLOW_EPHEMERAL_KEY", raising=False)
    with pytest.warns(RuntimeWarning):
        store = server._get_token_store()
    assert store is not None
