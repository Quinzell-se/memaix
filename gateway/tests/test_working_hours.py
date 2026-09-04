# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for connectors.working_hours — memaix-src card e21fde31."""

from __future__ import annotations

import pytest

from memaix_gateway.connectors.working_hours import (
    WorkingHoursStore,
    apply_working_hours,
    validate_week,
)


def test_apply_working_hours_returns_unchanged_when_week_empty():
    free = [{"start": "2026-01-05T00:00:00+00:00", "end": "2026-01-06T00:00:00+00:00"}]
    assert apply_working_hours(free, {}, "Europe/Stockholm") == free


def test_apply_working_hours_returns_unchanged_when_tz_empty():
    free = [{"start": "2026-01-05T00:00:00+00:00", "end": "2026-01-06T00:00:00+00:00"}]
    assert apply_working_hours(free, {"mon": [{"start": "09:00", "end": "17:00"}]}, "") == free


def test_apply_working_hours_intersects_single_day():
    # 2026-01-05 is a Monday. Stockholm is UTC+1 in January (no DST).
    free = [{"start": "2026-01-05T00:00:00+00:00", "end": "2026-01-06T00:00:00+00:00"}]
    week = {"mon": [{"start": "09:00", "end": "17:00"}]}
    result = apply_working_hours(free, week, "Europe/Stockholm")
    assert result == [{"start": "2026-01-05T08:00:00+00:00", "end": "2026-01-05T16:00:00+00:00"}]


def test_apply_working_hours_empty_day_excludes_it():
    # 2026-01-10 is a Saturday.
    free = [{"start": "2026-01-10T00:00:00+00:00", "end": "2026-01-11T00:00:00+00:00"}]
    week = {"mon": [{"start": "09:00", "end": "17:00"}], "sat": []}
    assert apply_working_hours(free, week, "Europe/Stockholm") == []


def test_apply_working_hours_no_windows_for_weekday_excludes_it():
    free = [{"start": "2026-01-10T00:00:00+00:00", "end": "2026-01-11T00:00:00+00:00"}]
    week = {"mon": [{"start": "09:00", "end": "17:00"}]}  # no "sat" key at all
    assert apply_working_hours(free, week, "Europe/Stockholm") == []


def test_apply_working_hours_spans_multiple_days():
    free = [{"start": "2026-01-05T00:00:00+00:00", "end": "2026-01-07T00:00:00+00:00"}]
    week = {
        "mon": [{"start": "09:00", "end": "17:00"}],
        "tue": [{"start": "09:00", "end": "17:00"}],
    }
    result = apply_working_hours(free, week, "Europe/Stockholm")
    assert result == [
        {"start": "2026-01-05T08:00:00+00:00", "end": "2026-01-05T16:00:00+00:00"},
        {"start": "2026-01-06T08:00:00+00:00", "end": "2026-01-06T16:00:00+00:00"},
    ]


def test_apply_working_hours_multiple_windows_same_day():
    free = [{"start": "2026-01-05T00:00:00+00:00", "end": "2026-01-06T00:00:00+00:00"}]
    week = {"mon": [{"start": "09:00", "end": "12:00"}, {"start": "13:00", "end": "17:00"}]}
    result = apply_working_hours(free, week, "Europe/Stockholm")
    assert result == [
        {"start": "2026-01-05T08:00:00+00:00", "end": "2026-01-05T11:00:00+00:00"},
        {"start": "2026-01-05T12:00:00+00:00", "end": "2026-01-05T16:00:00+00:00"},
    ]


def test_apply_working_hours_gap_narrower_than_window_is_clamped():
    free = [{"start": "2026-01-05T09:30:00+00:00", "end": "2026-01-05T10:00:00+00:00"}]
    week = {"mon": [{"start": "09:00", "end": "17:00"}]}
    result = apply_working_hours(free, week, "Europe/Stockholm")
    assert result == free


def test_apply_working_hours_24_00_end_of_day_sentinel():
    # "24:00" local means next-local-midnight, i.e. Mon 22:00-24:00 local
    # (Stockholm, UTC+1 in January) is UTC 21:00-23:00 the same UTC date.
    free = [{"start": "2026-01-05T00:00:00+00:00", "end": "2026-01-06T00:00:00+00:00"}]
    week = {"mon": [{"start": "22:00", "end": "24:00"}]}
    result = apply_working_hours(free, week, "Europe/Stockholm")
    assert result == [{"start": "2026-01-05T21:00:00+00:00", "end": "2026-01-05T23:00:00+00:00"}]


def test_validate_week_rejects_unknown_weekday_key():
    with pytest.raises(ValueError):
        validate_week({"funday": [{"start": "09:00", "end": "17:00"}]})


def test_validate_week_rejects_start_after_end():
    with pytest.raises(ValueError):
        validate_week({"mon": [{"start": "17:00", "end": "09:00"}]})


def test_validate_week_accepts_empty_week():
    validate_week({})


def test_validate_week_rejects_overlapping_windows_same_day():
    with pytest.raises(ValueError):
        validate_week(
            {"mon": [{"start": "09:00", "end": "12:00"}, {"start": "11:00", "end": "17:00"}]}
        )


def test_validate_week_accepts_adjacent_non_overlapping_windows():
    # touching but not overlapping (12:00 end == 12:00 start) is fine
    validate_week({"mon": [{"start": "09:00", "end": "12:00"}, {"start": "12:00", "end": "17:00"}]})


def test_apply_working_hours_across_spring_dst_transition():
    # 2026-03-29 is when Stockholm springs forward (02:00 -> 03:00 local).
    # A 09:00-17:00 local window that day is still 8h wall-clock, but only
    # 7h in UTC terms since the clocks jumped an hour during the night
    # before the window even opens.
    free = [{"start": "2026-03-29T00:00:00+00:00", "end": "2026-03-30T00:00:00+00:00"}]
    week = {"sun": [{"start": "09:00", "end": "17:00"}]}
    result = apply_working_hours(free, week, "Europe/Stockholm")
    # Before DST: UTC+1, after DST: UTC+2. 09:00-17:00 local on the
    # transition day is entirely after the 02:00 jump, so it's UTC+2 throughout.
    assert result == [{"start": "2026-03-29T07:00:00+00:00", "end": "2026-03-29T15:00:00+00:00"}]


@pytest.fixture()
def acl_with_vault(tmp_path):
    from memaix_gateway.acl import Acl

    return Acl(
        users={"alice": {"grants": {"proj": "owner"}}},
        projects={"proj": {"vault": str(tmp_path), "calendar": {"type": "caldav"}}},
    )


def test_store_get_returns_empty_dict_when_never_set(acl_with_vault):
    store = WorkingHoursStore(acl_with_vault, "proj", "alice")
    assert store.get() == {}


def test_store_set_then_get_roundtrips(acl_with_vault):
    store = WorkingHoursStore(acl_with_vault, "proj", "alice")
    week = {"mon": [{"start": "09:00", "end": "17:00"}]}
    store.set("Europe/Stockholm", week)
    assert store.get() == {"tz": "Europe/Stockholm", "week": week}


def test_store_set_rejects_unresolvable_timezone(acl_with_vault):
    store = WorkingHoursStore(acl_with_vault, "proj", "alice")
    with pytest.raises(Exception):
        store.set("Not/A/Zone", {})


def test_store_set_rejects_invalid_week(acl_with_vault):
    store = WorkingHoursStore(acl_with_vault, "proj", "alice")
    with pytest.raises(ValueError):
        store.set("Europe/Stockholm", {"mon": [{"start": "17:00", "end": "09:00"}]})
