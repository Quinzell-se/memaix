# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for booking.slotting — the logic that used to live in two browsers."""

from datetime import UTC, datetime, timedelta

import pytest

from memaix_gateway.booking.slotting import subdivide

STHLM = "Europe/Stockholm"


def _starts(slots):
    return [s["start"] for s in slots]


def test_whole_window_divides_evenly():
    out = subdivide(
        [{"start": "2026-09-08T14:00:00+00:00", "end": "2026-09-08T16:00:00+00:00"}],
        duration_min=30, tz=STHLM,
    )
    assert _starts(out) == [
        "2026-09-08T16:00:00+02:00",
        "2026-09-08T16:30:00+02:00",
        "2026-09-08T17:00:00+02:00",
        "2026-09-08T17:30:00+02:00",
    ]


def test_ragged_start_is_rounded_up_to_the_clock():
    """The bug this module exists for: a window starting 16:15 must offer
    16:30, not 16:15/16:45/17:15 — the leftovers of someone else's meeting."""
    out = subdivide(
        [{"start": "2026-10-01T14:15:00+00:00", "end": "2026-10-01T16:00:00+00:00"}],
        duration_min=30, tz=STHLM,
    )
    assert _starts(out) == [
        "2026-10-01T16:30:00+02:00",
        "2026-10-01T17:00:00+02:00",
        "2026-10-01T17:30:00+02:00",
    ]


def test_slot_never_overruns_the_window():
    out = subdivide(
        [{"start": "2026-09-08T14:00:00+00:00", "end": "2026-09-08T14:50:00+00:00"}],
        duration_min=30, tz=STHLM,
    )
    assert _starts(out) == ["2026-09-08T16:00:00+02:00"]


def test_slot_ending_exactly_at_window_end_still_fits():
    out = subdivide(
        [{"start": "2026-09-08T14:00:00+00:00", "end": "2026-09-08T14:30:00+00:00"}],
        duration_min=30, tz=STHLM,
    )
    assert len(out) == 1


def test_window_shorter_than_duration_yields_nothing():
    assert subdivide(
        [{"start": "2026-09-08T14:00:00+00:00", "end": "2026-09-08T14:20:00+00:00"}],
        duration_min=30, tz=STHLM,
    ) == []


def test_slots_never_span_two_windows():
    """The gap between windows is busy by definition, so 16:30 must not be
    offered by stitching the end of one window to the start of the next."""
    out = subdivide(
        [
            {"start": "2026-09-08T14:00:00+00:00", "end": "2026-09-08T14:30:00+00:00"},
            {"start": "2026-09-08T15:00:00+00:00", "end": "2026-09-08T15:30:00+00:00"},
        ],
        duration_min=30, tz=STHLM,
    )
    assert _starts(out) == ["2026-09-08T16:00:00+02:00", "2026-09-08T17:00:00+02:00"]


def test_overlapping_windows_do_not_offer_the_same_time_twice():
    """Two calendar sources can each report the same free time."""
    out = subdivide(
        [
            {"start": "2026-09-08T14:00:00+00:00", "end": "2026-09-08T15:00:00+00:00"},
            {"start": "2026-09-08T14:30:00+00:00", "end": "2026-09-08T15:30:00+00:00"},
        ],
        duration_min=30, tz=STHLM,
    )
    assert _starts(out) == [
        "2026-09-08T16:00:00+02:00",
        "2026-09-08T16:30:00+02:00",
        "2026-09-08T17:00:00+02:00",
    ]


def test_output_is_sorted_even_when_windows_are_not():
    out = subdivide(
        [
            {"start": "2026-09-09T14:00:00+00:00", "end": "2026-09-09T14:30:00+00:00"},
            {"start": "2026-09-08T14:00:00+00:00", "end": "2026-09-08T14:30:00+00:00"},
        ],
        duration_min=30, tz=STHLM,
    )
    assert _starts(out) == ["2026-09-08T16:00:00+02:00", "2026-09-09T16:00:00+02:00"]


def test_alignment_is_local_not_utc():
    """Kolkata is UTC+05:30. Aligning in UTC would put every slot on :30
    local — wrong everywhere the offset isn't a whole hour, and invisible
    from Stockholm."""
    out = subdivide(
        [{"start": "2026-09-08T04:20:00+00:00", "end": "2026-09-08T06:00:00+00:00"}],
        duration_min=30, tz="Asia/Kolkata",
    )
    assert [s["start"][11:16] for s in out] == ["10:00", "10:30", "11:00"]


def test_granularity_can_be_finer_than_duration():
    """A 60-minute meeting offered on a 30-minute grid overlaps itself by
    design — the host is offering more starting points, not more meetings."""
    out = subdivide(
        [{"start": "2026-09-08T14:00:00+00:00", "end": "2026-09-08T16:00:00+00:00"}],
        duration_min=60, tz=STHLM, granularity_min=30,
    )
    assert [s["start"][11:16] for s in out] == ["16:00", "16:30", "17:00"]


def test_empty_input_is_empty_output():
    assert subdivide([], duration_min=30, tz=STHLM) == []


@pytest.mark.parametrize("duration,granularity", [(0, 30), (30, 0), (-15, 30)])
def test_nonpositive_arguments_are_rejected(duration, granularity):
    with pytest.raises(ValueError):
        subdivide([], duration_min=duration, tz=STHLM, granularity_min=granularity)


def test_dst_fall_back_never_offers_the_same_reading_twice():
    """Stockholm repeats 02:00-03:00 on 2026-10-25. Two distinct instants
    both read "02:30", and a visitor picking one off a grid can't say which
    they meant — so only the first is offered."""
    out = subdivide(
        [{"start": "2026-10-24T22:00:00+00:00", "end": "2026-10-25T04:00:00+00:00"}],
        duration_min=30, tz=STHLM,
    )
    readings = [s["start"][:16] for s in out]
    assert len(readings) == len(set(readings))


def test_every_slot_is_exactly_as_long_as_it_claims():
    """Across the repeated hour a slot really can read "02:30 -> 02:00" —
    that is what the wall clock does that night, not a bug. What must hold
    is the thing a visitor is actually promised: thirty real minutes."""
    out = subdivide(
        [{"start": "2026-10-24T22:00:00+00:00", "end": "2026-10-25T04:00:00+00:00"}],
        duration_min=30, tz=STHLM,
    )
    for slot in out:
        span = datetime.fromisoformat(slot["end"]) - datetime.fromisoformat(slot["start"])
        assert span == timedelta(minutes=30), slot


def test_dst_fall_back_keeps_walking_forward_in_real_time():
    """Wall-clock stepping jumps 90 real minutes crossing 03:00 in autumn and
    then walks backwards onto the earlier 02:00, which loops forever. The
    offers must march strictly forward in real time and reach the end of the
    window."""
    out = subdivide(
        [{"start": "2026-10-24T22:00:00+00:00", "end": "2026-10-25T04:00:00+00:00"}],
        duration_min=30, tz=STHLM,
    )
    absolute = [datetime.fromisoformat(s["start"]).astimezone(UTC) for s in out]
    assert all(b > a for a, b in zip(absolute, absolute[1:]))
    assert _starts(out)[0] == "2026-10-25T00:00:00+02:00"
    assert _starts(out)[-1] == "2026-10-25T04:30:00+01:00"


def test_a_naive_window_is_refused_not_guessed_at():
    """Assuming a zone for a boundary that doesn't state one is how you book
    somebody at four in the morning."""
    with pytest.raises(ValueError):
        subdivide(
            [{"start": "2026-09-08T14:00:00", "end": "2026-09-08T16:00:00"}],
            duration_min=30, tz=STHLM,
        )


def test_a_slot_is_a_real_duration_not_a_wall_clock_one():
    """A 60-minute slot starting 01:30 local on the spring-forward night ends
    at 03:30 local, not 02:30 — the hour that doesn't exist can't be spent in
    a meeting. Wall-clock arithmetic would quietly sell 120 real minutes as
    an hour."""
    out = subdivide(
        [{"start": "2026-03-29T00:30:00+00:00", "end": "2026-03-29T02:30:00+00:00"}],
        duration_min=60, tz=STHLM, granularity_min=30,
    )
    first = out[0]
    assert first["start"][11:16] == "01:30"
    assert first["end"][11:16] == "03:30"


def test_dst_spring_forward_keeps_the_grid_on_the_clock():
    """Stockholm skips 02:00-03:00 on 2026-03-29. Slots after the jump must
    still sit on :00/:30 local, not be shifted by an hour."""
    out = subdivide(
        [{"start": "2026-03-29T01:00:00+00:00", "end": "2026-03-29T03:00:00+00:00"}],
        duration_min=30, tz=STHLM,
    )
    assert all(s["start"][14:16] in ("00", "30") for s in out)
