# SPDX-License-Identifier: AGPL-3.0-or-later
"""Server-level tests for nc_generate_report — connector wiring for the
pm_report -> .odt -> Nextcloud files pipeline (FEATURE-NEXTCLOUD-BACKEND.md
§8, Byggordning steg 7)."""

from __future__ import annotations

import zipfile
from io import BytesIO

import pytest

from memaix_gateway import server
from memaix_gateway.acl import AccessDenied, Acl
from memaix_gateway.outbox.queue import ActionQueue
from memaix_gateway.pm.store import PMStore
from memaix_gateway.safety.audit import AuditLog
from memaix_gateway.notify.store import NotifyStore
from memaix_gateway.rules.store import RulesStore
from memaix_gateway.search.store import EmbeddingStore
from memaix_gateway.timeline.store import ActionsStore
import memaix_gateway.connectors.registry as registry_mod
from memaix_gateway.connectors.registry import ConnectorRegistry, ConnectorSpec


class _FakeFilesBackend:
    def __init__(self):
        self.written: dict[str, bytes] = {}

    def write_binary(self, path, data):
        self.written[path.strip("/")] = data
        return f"ok: {path}"


@pytest.fixture()
def wired(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    (vault / "backlog").mkdir(parents=True)
    acl = Acl(
        users={
            "alice": {"grants": {"proj": "owner"}},
            "bob": {"grants": {"proj": "reader"}},
        },
        projects={"proj": {"vault": str(vault), "files": {"url": "https://nc.example.com/files/"}}},
    )
    AuditLog._clear_instances()
    monkeypatch.setattr(server, "_acl", acl)
    monkeypatch.setattr(server, "_audit", AuditLog.for_path(tmp_path / "audit.db"))
    monkeypatch.setattr(server, "_outbox_queue", ActionQueue.for_path(tmp_path / "outbox.db"))
    monkeypatch.setattr(server, "_timeline_store", ActionsStore.for_path(tmp_path / "actions.db"))
    monkeypatch.setattr(server, "_search_store", EmbeddingStore.for_path(tmp_path / "index.db"))
    monkeypatch.setattr(server, "_search_embedder", None)
    monkeypatch.setattr(server, "_search_embedder_loaded", True)
    monkeypatch.setattr(server, "_notify_store", NotifyStore.for_path(tmp_path / "notify.db"))
    monkeypatch.setattr(server, "_rules_store", RulesStore.for_path(tmp_path / "rules.db"))
    monkeypatch.setattr(server, "_pm_store", PMStore.for_path(tmp_path / "pm.db"))
    monkeypatch.setenv("MEMAIX_USER", "alice")
    server._rate_limiter._windows.clear()

    backend = _FakeFilesBackend()
    fake_registry = ConnectorRegistry()
    fake_registry.register(
        ConnectorSpec(type="webdav", capability="files", auth="shared", factory=lambda *a: backend)
    )
    monkeypatch.setattr(registry_mod, "_registry", fake_registry)
    return vault, acl, backend


def test_nc_generate_report_writes_odt_to_nextcloud(wired):
    _, _, backend = wired
    server.milestone_add("proj", "Beta launch", "2025-01-01")

    result = server.nc_generate_report("proj", "reports/status.odt")

    assert result["path"] == "reports/status.odt"
    assert "reports/status.odt" in backend.written
    data = backend.written["reports/status.odt"]
    zf = zipfile.ZipFile(BytesIO(data))
    content = zf.read("content.xml").decode()
    assert "Beta launch" in content


def test_nc_generate_report_respects_kind_and_audience(wired):
    _, _, backend = wired
    server.milestone_add("proj", "On track", "2999-01-01")
    server.milestone_add("proj", "Late", "2025-01-01")

    server.nc_generate_report("proj", "reports/status.odt", kind="milestones", audience="leadership")

    content = zipfile.ZipFile(BytesIO(backend.written["reports/status.odt"])).read("content.xml").decode()
    assert "Late" in content
    assert "On track" not in content


def test_nc_generate_report_requires_collaborator(wired, monkeypatch):
    monkeypatch.setenv("MEMAIX_USER", "bob")  # reader
    with pytest.raises(AccessDenied):
        server.nc_generate_report("proj", "reports/status.odt")


def test_nc_generate_report_is_audited(wired):
    server.nc_generate_report("proj", "reports/status.odt")
    tools = [e["tool"] for e in server._get_audit().tail(5)]
    assert "nc_generate_report" in tools
