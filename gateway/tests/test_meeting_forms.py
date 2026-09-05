# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for connectors.meeting_forms — memaix-src card 85854d2c."""

from __future__ import annotations

import pytest

from memaix_gateway.connectors.meeting_forms import MeetingFormsStore, validate_forms


@pytest.fixture()
def acl_with_vault(tmp_path):
    from memaix_gateway.acl import Acl

    return Acl(
        users={"alice": {"grants": {"proj": "owner"}}},
        projects={"proj": {"vault": str(tmp_path), "calendar": {"type": "caldav"}}},
    )


def _form(slug="video", provider="google_meet", label="Google Meet", **extra):
    return {"slug": slug, "provider": provider, "label": label, **extra}


def test_store_get_defaults_to_empty_when_never_set(acl_with_vault):
    store = MeetingFormsStore(acl_with_vault, "proj", "alice")
    assert store.get() == []


def test_store_set_then_get_roundtrips(acl_with_vault):
    store = MeetingFormsStore(acl_with_vault, "proj", "alice")
    store.set([_form()])
    result = store.get()
    assert result == [
        {"slug": "video", "provider": "google_meet", "label": "Google Meet", "config": {}, "default": True}
    ]


def test_store_is_scoped_per_user(acl_with_vault):
    alice = MeetingFormsStore(acl_with_vault, "proj", "alice")
    bob = MeetingFormsStore(acl_with_vault, "proj", "bob")
    alice.set([_form()])
    assert bob.get() == []


def test_delete_removes_one_form(acl_with_vault):
    store = MeetingFormsStore(acl_with_vault, "proj", "alice")
    store.set([_form(slug="a", label="A"), _form(slug="b", label="B", provider="zoom")])
    store.delete("a")
    slugs = [f["slug"] for f in store.get()]
    assert slugs == ["b"]


def test_delete_missing_slug_is_a_noop(acl_with_vault):
    store = MeetingFormsStore(acl_with_vault, "proj", "alice")
    store.set([_form()])
    store.delete("does-not-exist")
    assert len(store.get()) == 1


def test_delete_last_form_leaves_empty_list(acl_with_vault):
    store = MeetingFormsStore(acl_with_vault, "proj", "alice")
    store.set([_form()])
    store.delete("video")
    assert store.get() == []


# --- validate_forms ------------------------------------------------------


def test_validate_rejects_unknown_provider():
    with pytest.raises(ValueError, match="unknown provider"):
        validate_forms([_form(provider="webex")])


def test_validate_rejects_invalid_slug():
    with pytest.raises(ValueError, match="invalid slug"):
        validate_forms([_form(slug="Not Valid")])


def test_validate_rejects_duplicate_slugs():
    with pytest.raises(ValueError, match="duplicate slug"):
        validate_forms([_form(slug="a"), _form(slug="a", provider="zoom")])


def test_validate_rejects_missing_label():
    with pytest.raises(ValueError, match="label is required"):
        validate_forms([{"slug": "a", "provider": "zoom"}])


def test_validate_phone_requires_phone_number():
    with pytest.raises(ValueError, match="phone form requires config.phone_number"):
        validate_forms([_form(slug="p", provider="phone", label="Phone")])


def test_validate_phone_accepts_config_phone_number():
    result = validate_forms([_form(slug="p", provider="phone", label="Phone", config={"phone_number": "+46701234567"})])
    assert result[0]["config"] == {"phone_number": "+46701234567"}


def test_validate_phone_rejects_blank_phone_number():
    with pytest.raises(ValueError, match="phone form requires config.phone_number"):
        validate_forms([_form(slug="p", provider="phone", label="Phone", config={"phone_number": "   "})])


def test_validate_non_phone_config_is_discarded():
    result = validate_forms([_form(config={"anything": "ignored"})])
    assert result[0]["config"] == {}


def test_validate_rejects_multiple_defaults():
    with pytest.raises(ValueError, match="at most one"):
        validate_forms([
            _form(slug="a", default=True),
            _form(slug="b", provider="zoom", default=True),
        ])


def test_first_form_auto_promoted_default_when_none_marked():
    result = validate_forms([
        _form(slug="a", label="A"),
        _form(slug="b", provider="zoom", label="B"),
    ])
    assert result[0]["default"] is True
    assert result[1]["default"] is False


def test_explicit_default_is_respected():
    result = validate_forms([
        _form(slug="a", label="A"),
        _form(slug="b", provider="zoom", label="B", default=True),
    ])
    assert result[0]["default"] is False
    assert result[1]["default"] is True


def test_validate_empty_list_is_valid():
    assert validate_forms([]) == []


def test_validate_rejects_non_dict_item():
    with pytest.raises(ValueError, match="must be an object"):
        validate_forms(["not-a-dict"])


# --- ConsentStore migration: meeting_form_* columns ----------------------


def test_consent_store_has_meeting_form_columns(tmp_path):
    from memaix_gateway.booking.consent_store import ConsentStore

    store = ConsentStore(tmp_path / "consent.db")
    with store._connect() as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(booking_consent)").fetchall()}
    assert {"meeting_form_slug", "meeting_form_provider", "meeting_form_detail"} <= cols


def test_consent_store_record_and_get_roundtrips_meeting_form_columns(tmp_path):
    from memaix_gateway.booking.consent_store import ConsentStore

    store = ConsentStore(tmp_path / "consent.db")
    _row_id, manage_token = store.record(
        project="proj", host_user="alice", event_id="ev1", visitor_email="bob@example.com",
        consent_text="ok", consent_at=1000, meeting_end=2000,
        meeting_form_slug="video", meeting_form_provider="google_meet",
        meeting_form_detail="https://meet.google.com/abc-defg-hij",
    )
    row = store.get_by_manage_token(manage_token)
    assert row["meeting_form_slug"] == "video"
    assert row["meeting_form_provider"] == "google_meet"
    assert row["meeting_form_detail"] == "https://meet.google.com/abc-defg-hij"


def test_consent_store_meeting_form_columns_default_to_none(tmp_path):
    from memaix_gateway.booking.consent_store import ConsentStore

    store = ConsentStore(tmp_path / "consent.db")
    _row_id, manage_token = store.record(
        project="proj", host_user="alice", event_id="ev1", visitor_email="bob@example.com",
        consent_text="ok", consent_at=1000, meeting_end=2000,
    )
    row = store.get_by_manage_token(manage_token)
    assert row["meeting_form_slug"] is None
    assert row["meeting_form_provider"] is None
    assert row["meeting_form_detail"] is None
