# SPDX-License-Identifier: AGPL-3.0-or-later
"""Retention purge for booking data — memaix-src card 01cf3b74.

The card's decision: booking data is kept for 1 year after the *meeting*
date, then deleted. The only two places PII from a booking lives are the
calendar event itself and consent_store's log (see that module's docstring
for why both exist). This is the third independent background loop in
server.py, not folded into notify/scheduler.py's run_due or
calendar_cache's sync loop — same "failure isolation is worth another
task" reasoning those two already use, and this one's schedule (hourly,
driven by consent rows) has nothing in common with either.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from .consent_store import ConsentStore

logger = logging.getLogger(__name__)

DEFAULT_TICK_SECONDS = 3600  # gallring är inte tidskritisk; 1 år ± 1h spelar ingen roll


def purge_due(store: ConsentStore, acl_fn, resolve_dav_fn, now: datetime) -> int:
    """Delete the calendar event and scrub PII for every consent row whose
    meeting ended more than a year ago. Returns the number of rows purged.

    A single row's failure (event already gone, calendar temporarily
    unreachable) is logged and skipped, same isolation principle as
    calendar_cache.sync_all_due — one bad row never blocks the rest of the
    tick."""
    from ..tools import calendar as t_cal
    from ..tools.calendar import CalendarAuthRequired

    now_epoch = int(now.timestamp())
    purged = 0
    for row in store.due(now_epoch):
        row_id, project, host_user, event_id = row["id"], row["project"], row["host_user"], row["event_id"]
        try:
            if event_id:
                acl = acl_fn()
                try:
                    dav = resolve_dav_fn(project, host_user)
                    t_cal.calendar_delete(acl, host_user, project, event_id, _dav=dav)
                except CalendarAuthRequired:
                    # Host revoked calendar access since booking — nothing left
                    # to delete via that adapter. The consent row is still
                    # scrubbed below; a stale calendar entry isn't PII we
                    # control access to anymore.
                    pass
                except FileNotFoundError:
                    # Host already deleted the event manually before the
                    # retention mark — there's nothing left to purge on the
                    # calendar side, so scrub the row now instead of retrying
                    # forever (unlike CalendarAuthRequired, this is permanent).
                    pass
            store.mark_purged(row_id, now_epoch)
            purged += 1
        except Exception:
            logger.exception(
                "booking consent purge failed for row=%s project=%s host_user=%s",
                row_id, project, host_user,
            )
    return purged


async def consent_purge_loop(
    acl_fn, resolve_dav_fn, *, tick_seconds: int = DEFAULT_TICK_SECONDS, now_fn=None,
) -> None:
    """Check every *tick_seconds* for consent rows past retention and purge
    them. A tick's exception never kills the loop (same contract as
    notify/scheduler.py's scheduler_loop and calendar_cache's sync loop)."""
    import asyncio

    from .consent_store import get_consent_store

    while True:
        now = now_fn() if now_fn else datetime.now(timezone.utc)
        try:
            purge_due(get_consent_store(), acl_fn, resolve_dav_fn, now)
        except Exception:
            logger.warning("consent_purge_loop tick failed", exc_info=True)
        await asyncio.sleep(tick_seconds)
