# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for login-app/approved_clients.py — memaix-src card 4c8f32fe.

The real fix for the browser-scoped identity leak: Hydra's own "remember me"
ignores which OAuth client is asking, so login-app tracks (subject,
client_id) approval itself and only trusts Hydra's `skip` when this store
also agrees.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

# Load login-app/approved_clients.py by path — not part of the installed package.
_MOD_PATH = Path(__file__).resolve().parents[2] / "login-app" / "approved_clients.py"
_spec = importlib.util.spec_from_file_location("memaix_login_approved_clients", _MOD_PATH)
assert _spec and _spec.loader
approved_clients = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(approved_clients)


def test_is_approved_false_when_never_approved(tmp_path):
    db = str(tmp_path / "approved.db")
    assert approved_clients.is_approved("jimmy", "claude-client", db_path=db) is False


def test_approve_then_is_approved_true(tmp_path):
    db = str(tmp_path / "approved.db")
    approved_clients.approve("jimmy", "claude-client", db_path=db)
    assert approved_clients.is_approved("jimmy", "claude-client", db_path=db) is True


def test_approval_is_scoped_to_client_id(tmp_path):
    db = str(tmp_path / "approved.db")
    approved_clients.approve("jimmy", "claude-client", db_path=db)
    assert approved_clients.is_approved("jimmy", "mistral-client", db_path=db) is False


def test_approval_is_scoped_to_subject(tmp_path):
    db = str(tmp_path / "approved.db")
    approved_clients.approve("jimmy", "claude-client", db_path=db)
    assert approved_clients.is_approved("mistral-test", "claude-client", db_path=db) is False


def test_approve_is_idempotent(tmp_path):
    db = str(tmp_path / "approved.db")
    approved_clients.approve("jimmy", "claude-client", db_path=db)
    approved_clients.approve("jimmy", "claude-client", db_path=db)
    assert approved_clients.is_approved("jimmy", "claude-client", db_path=db) is True


def test_is_approved_false_for_empty_client_id_even_if_approved_empty(tmp_path):
    db = str(tmp_path / "approved.db")
    approved_clients.approve("jimmy", "", db_path=db)
    assert approved_clients.is_approved("jimmy", "", db_path=db) is False


def test_creates_parent_directory_if_missing(tmp_path):
    db = str(tmp_path / "nested" / "dir" / "approved.db")
    approved_clients.approve("jimmy", "claude-client", db_path=db)
    assert approved_clients.is_approved("jimmy", "claude-client", db_path=db) is True
