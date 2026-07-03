# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for server.reload_acl — the cache-invalidation hook the admin write path
(AclWriter, MEX-025) relies on so an acl.yaml rewrite takes effect without a
gateway restart."""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture()
def server_mod(tmp_path, monkeypatch):
    """Import the server module against a temp config dir with a writable acl.yaml."""
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    (cfg_dir / "brand.yaml").write_text("name: test\n")
    (cfg_dir / "memaix.yaml").write_text("memaix: {}\n")
    (cfg_dir / "acl.yaml").write_text(
        "users:\n  alice:\n    grants: {acme: reader}\n"
        "projects:\n  acme:\n    vault: /tmp/acme\n"
    )
    monkeypatch.setenv("MEMAIX_CONFIG_DIR", str(cfg_dir))
    import memaix_gateway.config as config
    importlib.reload(config)
    import memaix_gateway.server as server
    importlib.reload(server)
    yield server, cfg_dir
    # Leave globals clean for other tests.
    server._acl = None


def test_reload_acl_picks_up_disk_changes(server_mod):
    server, cfg_dir = server_mod
    acl = server._get_acl()
    assert acl.grants("alice").get("acme") == "reader"

    # Rewrite acl.yaml on disk (as AclWriter would).
    (cfg_dir / "acl.yaml").write_text(
        "users:\n  alice:\n    grants: {acme: owner}\n"
        "projects:\n  acme:\n    vault: /tmp/acme\n"
    )
    # Stale cache still returns the old role.
    assert server._get_acl().grants("alice").get("acme") == "reader"

    # After reload, the change is visible.
    reloaded = server.reload_acl()
    assert reloaded.grants("alice").get("acme") == "owner"
    assert server._get_acl().grants("alice").get("acme") == "owner"


def test_reload_acl_applies_disable(server_mod):
    server, cfg_dir = server_mod
    server._get_acl().enforce("alice", "acme", "reader")  # ok before

    (cfg_dir / "acl.yaml").write_text(
        "users:\n  alice:\n    grants: {acme: reader}\n    disabled: true\n"
        "projects:\n  acme:\n    vault: /tmp/acme\n"
    )
    server.reload_acl()
    from memaix_gateway.acl import AccessDenied
    with pytest.raises(AccessDenied):
        server._get_acl().enforce("alice", "acme", "reader")
