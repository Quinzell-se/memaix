# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for connectors.meeting_types — memaix-src card d0a1f633."""

from __future__ import annotations

import pytest

from memaix_gateway.connectors.meeting_types import MeetingTypesStore, validate_types


@pytest.fixture()
def acl_with_vault(tmp_path):
    from memaix_gateway.acl import Acl

    return Acl(
        users={"alice": {"grants": {"proj": "owner"}}},
        projects={"proj": {"vault": str(tmp_path), "calendar": {"type": "caldav"}}},
    )


def _type(slug="quick", name="Quick sync", duration_min=30, **extra):
    return {"slug": slug, "name": name, "duration_min": duration_min, **extra}


def test_store_get_defaults_to_empty_when_never_set(acl_with_vault):
    store = MeetingTypesStore(acl_with_vault, "proj", "alice")
    assert store.get() == []


def test_store_set_then_get_roundtrips(acl_with_vault):
    store = MeetingTypesStore(acl_with_vault, "proj", "alice")
    store.set([_type()])
    result = store.get()
    assert result == [
        {"slug": "quick", "name": "Quick sync", "duration_min": 30, "interval_min": 30, "default": True}
    ]


def test_interval_min_defaults_to_duration_min(acl_with_vault):
    store = MeetingTypesStore(acl_with_vault, "proj", "alice")
    store.set([_type(duration_min=45)])
    assert store.get()[0]["interval_min"] == 45


def test_interval_min_can_differ_from_duration(acl_with_vault):
    store = MeetingTypesStore(acl_with_vault, "proj", "alice")
    store.set([_type(interval_min=60)])
    assert store.get()[0]["interval_min"] == 60


def test_first_type_auto_promoted_default_when_none_marked(acl_with_vault):
    store = MeetingTypesStore(acl_with_vault, "proj", "alice")
    store.set([_type(slug="a", name="A"), _type(slug="b", name="B")])
    result = store.get()
    assert result[0]["default"] is True
    assert result[1]["default"] is False


def test_explicit_default_is_respected(acl_with_vault):
    store = MeetingTypesStore(acl_with_vault, "proj", "alice")
    store.set([_type(slug="a", name="A"), _type(slug="b", name="B", default=True)])
    result = store.get()
    assert result[0]["default"] is False
    assert result[1]["default"] is True


def test_store_is_scoped_per_user(acl_with_vault):
    alice = MeetingTypesStore(acl_with_vault, "proj", "alice")
    bob = MeetingTypesStore(acl_with_vault, "proj", "bob")
    alice.set([_type()])
    assert bob.get() == []


def test_delete_removes_one_type(acl_with_vault):
    store = MeetingTypesStore(acl_with_vault, "proj", "alice")
    store.set([_type(slug="a", name="A"), _type(slug="b", name="B")])
    store.delete("a")
    slugs = [t["slug"] for t in store.get()]
    assert slugs == ["b"]


def test_delete_missing_slug_is_a_noop(acl_with_vault):
    store = MeetingTypesStore(acl_with_vault, "proj", "alice")
    store.set([_type()])
    store.delete("does-not-exist")
    assert len(store.get()) == 1


def test_delete_last_type_leaves_empty_list(acl_with_vault):
    store = MeetingTypesStore(acl_with_vault, "proj", "alice")
    store.set([_type()])
    store.delete("quick")
    assert store.get() == []


def test_delete_default_type_promotes_another(acl_with_vault):
    store = MeetingTypesStore(acl_with_vault, "proj", "alice")
    store.set([_type(slug="a", name="A"), _type(slug="b", name="B")])
    store.delete("a")
    result = store.get()
    assert result == [
        {"slug": "b", "name": "B", "duration_min": 30, "interval_min": 30, "default": True}
    ]


def test_validate_rejects_invalid_slug():
    with pytest.raises(ValueError, match="invalid slug"):
        validate_types([_type(slug="Not Valid")])


def test_validate_rejects_duplicate_slug():
    with pytest.raises(ValueError, match="duplicate slug"):
        validate_types([_type(slug="a", name="A"), _type(slug="a", name="B")])


def test_validate_rejects_missing_name():
    with pytest.raises(ValueError, match="name is required"):
        validate_types([{"slug": "a", "duration_min": 30}])


def test_validate_rejects_duration_min_out_of_range():
    with pytest.raises(ValueError, match="duration_min"):
        validate_types([_type(duration_min=0)])
    with pytest.raises(ValueError, match="duration_min"):
        validate_types([_type(duration_min=43201)])


def test_validate_rejects_non_int_duration_min():
    with pytest.raises(ValueError, match="duration_min"):
        validate_types([_type(duration_min="30")])


def test_validate_rejects_multiple_defaults():
    with pytest.raises(ValueError, match="at most one"):
        validate_types([
            _type(slug="a", name="A", default=True),
            _type(slug="b", name="B", default=True),
        ])


def test_validate_accepts_max_duration():
    result = validate_types([_type(duration_min=43200)])
    assert result[0]["duration_min"] == 43200


def test_validate_empty_list_is_valid():
    assert validate_types([]) == []


def test_validate_rejects_non_dict_item():
    with pytest.raises(ValueError, match="must be an object"):
        validate_types(["not-a-dict"])
