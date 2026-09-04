# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-user bookable working hours — memaix-src backlog card e21fde31.

A recurring weekly schedule of which local times are open for booking at
all, independent of the calendar's busy/free truth (calendar_free_busy /
EventOverrideStore / OverrideStore). This module only ever *subtracts* from
already-free time — it never marks a busy block free. That single direction
is what keeps this concern from ever colliding with a forced-busy event
override from card c7698ff3: a busy interval is never even offered to this
filter, since it operates on free_slots() output, not on the busy list.

No stored schedule (or an unconfigured store) means every time is bookable
— this feature must not retroactively restrict existing users who never
opted in.

Storage: one JSON file per (project, user) in the project vault, same
convention as calendar_overrides.py.

Explicitly out of scope for v1 (see the card's design discussion):
holidays/date-specific exceptions, per-meeting-type schedules, buffers/
min-notice/slot granularity, and windows that cross local midnight.
"""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .aggregate import to_utc

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _working_hours_path(acl, project: str, user: str) -> Path:
    vault = acl.resource(project, "vault")
    if not vault:
        raise ValueError(f"project {project!r} has no vault configured")
    directory = Path(vault) / "working_hours"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{user}.json"


def _parse_hhmm(value: str) -> time:
    hour, minute = value.split(":")
    hour_i, minute_i = int(hour), int(minute)
    if hour_i == 24 and minute_i == 0:
        return time(23, 59, 59, 999999)  # end-of-day sentinel, see _day_windows_utc
    return time(hour_i, minute_i)


def validate_week(week: dict) -> None:
    """Raise ValueError if *week* is not a valid schedule shape."""
    if not set(week.keys()) <= set(WEEKDAYS):
        raise ValueError(f"unknown weekday key(s): {sorted(set(week.keys()) - set(WEEKDAYS))}")
    for day, windows in week.items():
        parsed = []
        for w in windows:
            start, end = _parse_hhmm(w["start"]), _parse_hhmm(w["end"])
            if start >= end:
                raise ValueError(f"{day}: start {w['start']!r} must be before end {w['end']!r}")
            parsed.append((start, end, w))
        parsed.sort(key=lambda p: (p[0], p[1]))
        for (start_a, end_a, w_a), (start_b, end_b, w_b) in zip(parsed, parsed[1:]):
            if start_b < end_a:
                raise ValueError(
                    f"{day}: window {w_a['start']!r}-{w_a['end']!r} overlaps "
                    f"{w_b['start']!r}-{w_b['end']!r}"
                )


class WorkingHoursStore:
    def __init__(self, acl, project: str, user: str) -> None:
        self._path = _working_hours_path(acl, project, user)

    def get(self) -> dict:
        """{} (no tz/week) if never configured — callers treat that as
        wide-open, no filtering."""
        if not self._path.exists():
            return {}
        return json.loads(self._path.read_text())

    def set(self, tz: str, week: dict) -> None:
        ZoneInfo(tz)  # raises ZoneInfoNotFoundError on an unresolvable tz
        validate_week(week)
        self._path.write_text(json.dumps({"tz": tz, "week": week}))


def _day_windows_utc(week: dict, tz: ZoneInfo, local_day: date) -> list[tuple[datetime, datetime]]:
    """The given local calendar day's bookable windows, each localized to
    *tz* and converted to UTC. [] if that weekday has no windows."""
    windows = week.get(WEEKDAYS[local_day.weekday()], [])
    out = []
    for w in windows:
        start_t, end_t = _parse_hhmm(w["start"]), _parse_hhmm(w["end"])
        start_local = datetime.combine(local_day, start_t, tzinfo=tz)
        if end_t == time(23, 59, 59, 999999):  # "24:00" sentinel = next midnight
            end_local = datetime.combine(local_day + timedelta(days=1), time(0, 0), tzinfo=tz)
        else:
            end_local = datetime.combine(local_day, end_t, tzinfo=tz)
        out.append((start_local.astimezone(ZoneInfo("UTC")), end_local.astimezone(ZoneInfo("UTC"))))
    return out


def apply_working_hours(free: list[dict], week: dict, tz: str) -> list[dict]:
    """Intersect each free {start, end} gap with the bookable local windows
    it overlaps. An empty *week* (or falsy *tz*) means wide-open — *free* is
    returned unchanged. Pure: UTC ISO-8601 strings in, UTC ISO-8601 strings
    out, same shape as aggregate.free_slots()."""
    if not week or not tz:
        return free

    zone = ZoneInfo(tz)
    out: list[dict] = []
    for gap in free:
        gap_start, gap_end = to_utc(gap["start"]), to_utc(gap["end"])
        day = gap_start.astimezone(zone).date()
        last_day = gap_end.astimezone(zone).date()
        while day <= last_day:
            for w_start, w_end in _day_windows_utc(week, zone, day):
                start = max(gap_start, w_start)
                end = min(gap_end, w_end)
                if start < end:
                    out.append({"start": start.isoformat(), "end": end.isoformat()})
            day += timedelta(days=1)
    out.sort(key=lambda s: s["start"])
    return out
