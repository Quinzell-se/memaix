# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the memaix_gateway.doctor module."""

from __future__ import annotations

import os

import pytest

from memaix_gateway import config as cfg_module
from memaix_gateway.doctor import (
    _check_config_parses,
    _check_oauth_sub_unique,
    _check_owner_per_project,
    _check_rbac_isolation,
    _check_vault_writable,
    _FAIL,
    _PASS,
    _WARN,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _set_config_dir(monkeypatch, tmp_path, acl_yaml: str, memaix_yaml: str = "", brand_yaml: str = ""):
    """Write minimal config files and point config.CONFIG_DIR at tmp_path."""
    (tmp_path / "acl.yaml").write_text(acl_yaml)
    (tmp_path / "memaix.yaml").write_text(memaix_yaml or "server:\n  bind: '0.0.0.0:8080'\n")
    (tmp_path / "brand.yaml").write_text(brand_yaml or "brand:\n  name: Test\n")
    monkeypatch.setattr(cfg_module, "CONFIG_DIR", tmp_path)


# ---------------------------------------------------------------------------
# config_parses
# ---------------------------------------------------------------------------


def test_config_parses_pass(monkeypatch, tmp_path):
    _set_config_dir(monkeypatch, tmp_path, "users: {}\nprojects: {}\n")
    check = _check_config_parses()
    assert check.status == _PASS


def test_config_parses_fail_on_invalid_yaml(monkeypatch, tmp_path):
    (tmp_path / "acl.yaml").write_text(": this is: invalid: yaml: {{")
    (tmp_path / "memaix.yaml").write_text("")
    (tmp_path / "brand.yaml").write_text("")
    monkeypatch.setattr(cfg_module, "CONFIG_DIR", tmp_path)
    check = _check_config_parses()
    assert check.status == _FAIL


# ---------------------------------------------------------------------------
# rbac_isolation
# ---------------------------------------------------------------------------


def test_rbac_isolation_passes():
    """Synthetic ACL with no users — ghost user must be denied."""
    check = _check_rbac_isolation()
    assert check.status == _PASS


# ---------------------------------------------------------------------------
# owner_per_project
# ---------------------------------------------------------------------------


def test_owner_per_project_pass(monkeypatch, tmp_path):
    acl_yaml = """
users:
  alice:
    oauth_sub: "alice@example.com"
    grants:
      proj_a: owner
projects:
  proj_a:
    vault: /tmp/x
"""
    _set_config_dir(monkeypatch, tmp_path, acl_yaml)
    checks = _check_owner_per_project()
    assert all(c.status == _PASS for c in checks)


def test_owner_per_project_warns_if_missing(monkeypatch, tmp_path):
    acl_yaml = """
users:
  bob:
    oauth_sub: "bob@example.com"
    grants:
      proj_b: collaborator
projects:
  proj_b:
    vault: /tmp/y
"""
    _set_config_dir(monkeypatch, tmp_path, acl_yaml)
    checks = _check_owner_per_project()
    statuses = {c.status for c in checks}
    assert _WARN in statuses
    assert _FAIL not in statuses


def test_owner_per_project_no_projects_passes(monkeypatch, tmp_path):
    _set_config_dir(monkeypatch, tmp_path, "users: {}\nprojects: {}\n")
    checks = _check_owner_per_project()
    assert all(c.status == _PASS for c in checks)


# ---------------------------------------------------------------------------
# oauth_sub_unique
# ---------------------------------------------------------------------------


def test_oauth_sub_unique_pass(monkeypatch, tmp_path):
    acl_yaml = """
users:
  u1:
    oauth_sub: "a@example.com"
    grants: {}
  u2:
    oauth_sub: "b@example.com"
    grants: {}
projects: {}
"""
    _set_config_dir(monkeypatch, tmp_path, acl_yaml)
    check = _check_oauth_sub_unique()
    assert check.status == _PASS


def test_oauth_sub_unique_fails_on_dup(monkeypatch, tmp_path):
    acl_yaml = """
users:
  u1:
    oauth_sub: "same@example.com"
    grants: {}
  u2:
    oauth_sub: "same@example.com"
    grants: {}
projects: {}
"""
    _set_config_dir(monkeypatch, tmp_path, acl_yaml)
    check = _check_oauth_sub_unique()
    assert check.status == _FAIL
    assert "same@example.com" in check.message


# ---------------------------------------------------------------------------
# vault_writable
# ---------------------------------------------------------------------------


def test_vault_writable_pass(monkeypatch, tmp_path):
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()

    acl_yaml = f"""
users: {{}}
projects:
  myproj:
    vault: "{vault_dir}"
"""
    _set_config_dir(monkeypatch, tmp_path, acl_yaml)
    checks = _check_vault_writable()
    assert len(checks) == 1
    assert checks[0].status == _PASS


def test_vault_writable_fail_nonexistent(monkeypatch, tmp_path):
    acl_yaml = """
users: {}
projects:
  badproj:
    vault: /nonexistent/path/that/does/not/exist
"""
    _set_config_dir(monkeypatch, tmp_path, acl_yaml)
    checks = _check_vault_writable()
    assert any(c.status == _FAIL for c in checks)


def test_vault_writable_skip_when_no_vaults(monkeypatch, tmp_path):
    _set_config_dir(monkeypatch, tmp_path, "users: {}\nprojects:\n  nostore:\n    mailbox: null\n")
    checks = _check_vault_writable()
    # No vault keys → SKIP
    assert all(c.status in ("SKIP", _PASS) for c in checks)
