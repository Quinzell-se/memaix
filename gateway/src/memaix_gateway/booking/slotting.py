# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cut free windows into bookable slots, aligned to the local clock.

`calendar_find_free` answers with *windows* — "you are free 16:00–18:00" —
not with times a visitor can click. Something has to divide them, and until
now that something was the browser: memaix.se/boka and jimlov.se/boka each
carried their own copy. Two copies meant two places for a bug to live and no
way to write a test, which is exactly how both sites shipped the same broken
slot grid on the same day.

It also produced offers no human would make. Dividing a window from its own
left edge means a meeting that overran to 16:15 leaves the next visitor
looking at 16:15, 16:45, 17:15 — the leftovers of someone else's calendar.
People book on the clock, so slots start on the clock: `granularity_min`
(default 30) sets the grid, the window's start is rounded *up* onto it, and
the quarter hour is simply lost. That is the correct price.

Alignment is computed in the host's local timezone, not UTC. India is +05:30
and Nepal +05:45; aligning in UTC would put every Indian slot on :00/:30 UTC
and therefore on :30/:00 local — subtly wrong everywhere the offset is not a
whole hour, and invisible from Stockholm.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

DEFAULT_GRANULARITY_MIN = 30


def _utc(moment: datetime) -> datetime:
    """The same instant, expressed absolutely — safe to do duration maths on."""
    return moment.astimezone(timezone.utc)


def _require_aware(value: str) -> datetime:
    """Parse a window boundary, refusing one that doesn't say when it is.

    Every caller today comes through calendar_find_free, which normalises to
    UTC first, so this never fires in practice. It exists because a naive
    string would otherwise surface as `TypeError: can't compare offset-naive
    and offset-aware datetimes` from somewhere deep in the loop — a 500 on a
    public endpoint, blamed on the wrong module. Assuming a zone instead
    would be worse: that's how you book someone at 04:00.
    """
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is None:
        raise ValueError(f"window boundary has no timezone: {value!r}")
    return moment


def _align_up(moment: datetime, granularity: timedelta, tz: ZoneInfo) -> datetime:
    """The first instant at or after *moment* that sits on the local grid.

    Measured from local midnight of *moment*'s own day rather than from the
    epoch, so a DST shift can't slide the grid off :00/:30 for the rest of
    the day.

    The result stays in *tz*. Windows arrive in UTC, but a slot is an offer
    made to a human, and "16:00+02:00" is the offer — handing back
    "14:00+00:00" would be the same instant expressed as something nobody
    agreed to meet at.
    """
    local = moment.astimezone(tz)
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    elapsed = local - midnight
    steps = -(-elapsed // granularity)  # ceiling division
    candidate = midnight + steps * granularity

    # `datetime.__add__` resets fold to 0, so on the autumn night the sum
    # always names the FIRST of the two 02:00s — an hour before the moment we
    # were asked to round up from. Unguarded that walks the caller backwards
    # and loops forever. When the grid point we landed on is ambiguous, take
    # the later of its two readings.
    if _utc(candidate) < _utc(moment):
        candidate = candidate.replace(fold=1)

    # The round trip through UTC normalises a wall time the local clock never
    # actually shows. On a spring-forward night an hourly grid lands on 02:00,
    # an hour that doesn't exist; left alone it would be published as
    # "02:00+01:00" — the correct instant wearing a name nobody could read off
    # a wall. Normalised, it comes back as the 03:00 it really is.
    return _utc(candidate).astimezone(tz)


def subdivide(
    windows: list[dict],
    duration_min: int,
    tz: str,
    granularity_min: int = DEFAULT_GRANULARITY_MIN,
) -> list[dict]:
    """Turn free {start, end} windows into bookable {start, end} slots.

    Slots are `duration_min` long, start on a `granularity_min` grid in *tz*,
    and never extend past their window's end. Windows are consumed
    independently — a slot never spans two of them, since the gap between is
    busy time by definition. Output is sorted and free of duplicates, so
    overlapping windows from different calendar sources can't offer the same
    time twice.

    Input and output are ISO-8601 strings, matching calendar_find_free's
    shape so this can sit directly behind it. Window boundaries must carry a
    UTC offset; a naive one raises rather than being guessed at.
    """
    if duration_min <= 0 or granularity_min <= 0:
        raise ValueError("duration_min and granularity_min must be positive")

    zone = ZoneInfo(tz)
    step = timedelta(minutes=granularity_min)
    length = timedelta(minutes=duration_min)

    starts: set[datetime] = set()
    labels: set[str] = set()
    for window in windows:
        start = _require_aware(window["start"])
        end = _require_aware(window["end"])
        cursor = _align_up(start, step, zone)
        # Stepping and measuring are deliberately different operations. The
        # grid is a wall-clock thing — 16:00, 16:30 — so the offered times sit
        # on local time. A meeting's length is a real-duration thing, so the
        # fit check and the end time are computed in UTC. Doing both in wall
        # time would make a slot straddling a DST gap 90 real minutes long
        # while still reading "30 min".
        while _utc(cursor) + length <= end:
            # One offer per wall-clock reading. On the autumn night 02:00
            # happens twice, an hour apart, and "02:00" then means two
            # different meetings — unanswerable for a visitor picking a time
            # off a grid. The second one is dropped: an hour of availability
            # lost once a year, at two in the morning, in exchange for every
            # published time meaning exactly one thing.
            label = cursor.replace(tzinfo=None).isoformat()
            if label not in labels:
                labels.add(label)
                starts.add(cursor)
            # Advance in UTC, then land back on the local grid. Stepping in
            # local time alone is naive wall-clock arithmetic: `datetime +
            # timedelta` keeps the old offset and never sets `fold`, so
            # crossing 03:00 in autumn jumps 90 real minutes and skips the
            # repeated hour entirely. Going via UTC makes the walk monotonic
            # in real time; re-aligning keeps it on :00/:30 regardless.
            nxt = _align_up(_utc(cursor) + step, step, zone)
            # Belt and braces. The walk is monotonic by construction, but the
            # first attempt at this loop wasn't and the symptom was a hung
            # request rather than a failed one — a test suite that never
            # finishes, a worker that never answers. A wrong answer can be
            # read; a hang can only be waited on.
            if _utc(nxt) <= _utc(cursor):
                raise RuntimeError(f"slot walk stopped advancing at {cursor.isoformat()}")
            cursor = nxt

    return [
        {
            "start": s.isoformat(),
            "end": (_utc(s) + length).astimezone(zone).isoformat(),
        }
        for s in sorted(starts)
    ]
