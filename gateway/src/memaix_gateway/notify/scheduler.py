# SPDX-License-Identifier: AGPL-3.0-or-later
"""Scheduler — figure out when the next brief is due and run it once, exactly.

See docs/FEATURE-PROACTIVE-BRIEF.md §7. `next_brief_epoch`/`run_due` are pure
functions taking `now` explicitly so they're deterministically testable;
`scheduler_loop` is the thin asyncio wrapper that calls them on a tick.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


def next_brief_epoch(prefs: dict, now: datetime) -> int:
    """Next UTC epoch (int seconds) for prefs['brief_time'] in prefs['timezone'],
    strictly after *now*."""
    from zoneinfo import ZoneInfo
    try:
        tz = ZoneInfo(prefs.get("timezone", "UTC"))
    except Exception:
        tz = timezone.utc

    hh, mm = (prefs.get("brief_time") or "07:00").split(":")
    local_now = now.astimezone(tz)
    candidate = local_now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
    if candidate <= local_now:
        candidate += timedelta(days=1)
    return int(candidate.astimezone(timezone.utc).timestamp())


def run_due(store, deliver_fn, now: datetime) -> int:
    """Claim and run every (user, slot) whose next_run has passed.

    deliver_fn(user, prefs, now) does the actual delivery — this function
    only owns scheduling: claiming (so a second worker on the same DB can't
    double-fire the same slot) and computing the next run time.
    Returns the number of slots actually delivered this tick.
    """
    now_epoch = int(now.timestamp())
    ran = 0
    for row in store.due(now_epoch):
        user, slot, old_next = row["memaix_user"], row["slot"], row["next_run"]
        prefs = store.get_prefs(user)
        effective_prefs = prefs or {"timezone": "UTC", "brief_time": "07:00"}
        new_next = next_brief_epoch(effective_prefs, now)

        if not store.claim(user, slot, old_next, new_next):
            continue  # another worker/tick already claimed this slot

        if not prefs or not prefs.get("enabled"):
            continue  # rescheduled forward; nothing to deliver while disabled

        try:
            deliver_fn(user, prefs, now)
            ran += 1
        except Exception:
            logger.warning("brief delivery failed for user=%r slot=%r", user, slot, exc_info=True)
        finally:
            store.mark_run(user, slot, now_epoch)
    return ran


async def scheduler_loop(store, deliver_fn, *, interval: int = 60, now_fn=None) -> None:
    """Call run_due() every *interval* seconds, forever. A tick's exception
    never kills the loop. now_fn is injectable for tests."""
    while True:
        now = now_fn() if now_fn else datetime.now(timezone.utc)
        try:
            run_due(store, deliver_fn, now)
        except Exception:
            logger.warning("scheduler tick failed", exc_info=True)
        await asyncio.sleep(interval)
