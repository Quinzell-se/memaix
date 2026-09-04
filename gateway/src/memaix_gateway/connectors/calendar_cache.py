# SPDX-License-Identifier: AGPL-3.0-or-later
"""Periodic calendar busy/free cache — memaix-src backlog card 4daa20e2.

Decision recorded on the card 2026-09-04: no realtime querying of external
calendar sources. Busy/free state is synced into a per-(project, user)
cache file every 5-15 minutes by calendar_sync_loop; every read
(calendar_free_busy, and later the public booking page) reads the cache,
never the live source. This trades a few minutes of staleness for a
booking page that stays fast and up even when a calendar source is
temporarily unreachable — the source-down scenario becomes "use the last
successful sync" instead of a hard per-request failure.

Mirrors notify/scheduler.py's split: pure scheduling functions
(is_due/sync_all_due) that take `now` explicitly and are deterministically
testable, plus a thin asyncio wrapper (calendar_sync_loop) for the real
process.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .aggregate import BusyInterval, CalendarEvent, CalendarSourceError, events_from_backend, merge_busy
from .registry import ConnectorRegistry

logger = logging.getLogger(__name__)

DEFAULT_SYNC_WINDOW = timedelta(days=90)
DEFAULT_SYNC_INTERVAL = timedelta(minutes=10)  # within the agreed 5-15 min band


def _cache_path(acl, project: str, user: str) -> Path:
    vault = acl.resource(project, "vault")
    if not vault:
        raise ValueError(f"project {project!r} has no vault configured")
    directory = Path(vault) / "calendar_cache"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{user}.json"


def read_cache(acl, project: str, user: str) -> dict | None:
    """Return the last-synced cache dict, or None if this (project, user)
    has never been synced."""
    path = _cache_path(acl, project, user)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _write_cache(acl, project: str, user: str, data: dict) -> None:
    _cache_path(acl, project, user).write_text(json.dumps(data))


def sync_user_calendar(
    acl,
    token_store,
    project: str,
    user: str,
    *,
    registry: ConnectorRegistry | None = None,
    now: datetime | None = None,
    window: timedelta = DEFAULT_SYNC_WINDOW,
) -> dict:
    """Query every enabled source (calendar_sources.resolve_effective_sources —
    registry.get_all() filtered by the user's disabled-set, plus any public
    .ics links they've added), merge their
    busy intervals, and write the result to the cache file.

    Never raises for a single source's failure — those are recorded
    per-source in the returned/written `errors` list. A source that failed
    simply contributes nothing to this sync's busy view; the *previous*
    cache write (if any) is overwritten regardless, since a stale full
    cache is judged safer to reason about than a partially-merged one
    (see the card's fail-closed-at-read-time note in calendar_free_busy)."""
    from .calendar_sources import resolve_effective_sources
    from .registry import default_registry

    now = now or datetime.now(timezone.utc)
    registry = registry or default_registry()
    start, end = now, now + window

    sources = resolve_effective_sources(acl, token_store, project, user, registry=registry)
    events: list[CalendarEvent] = []
    errors: list[dict] = []
    for label, backend in sources:
        try:
            events.extend(events_from_backend(backend, label, start, end))
        except CalendarSourceError as exc:
            errors.append({"source": label, "error": str(exc.cause)})

    # "busy" keeps its pre-c7698ff3 meaning: every fetched event counts,
    # regardless of source_busy — the per-event override resolution (incl.
    # honoring source_busy) happens at calendar_free_busy read time, against
    # "events" below, not here.
    merged = merge_busy([BusyInterval(e.start, e.end, e.source) for e in events])
    data = {
        "synced_at": now.isoformat(),
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "events": [
            {
                "uid": e.uid,
                "start": e.start.isoformat(),
                "end": e.end.isoformat(),
                "source": e.source,
                "title": e.title,
                "series_id": e.series_id,
                "is_exception": e.is_exception,
                "source_busy": e.source_busy,
                "stable_id": e.stable_id,
            }
            for e in events
        ],
        "busy": [
            {"start": b.start.isoformat(), "end": b.end.isoformat(), "source": b.source} for b in merged
        ],
        "source_count": len(sources),
        "errors": errors,
    }
    _write_cache(acl, project, user, data)
    return data


def is_due(cache: dict | None, now: datetime, interval: timedelta = DEFAULT_SYNC_INTERVAL) -> bool:
    """True if *cache* is missing or older than *interval*."""
    if cache is None:
        return True
    synced_at = datetime.fromisoformat(cache["synced_at"])
    return now - synced_at >= interval


def iter_calendar_targets(acl) -> list[tuple[str, str]]:
    """Every (project, user) pair with both a configured calendar resource
    and a grant on that project, in stable sorted order."""
    targets: list[tuple[str, str]] = []
    for project, cfg in sorted(acl.projects.items()):
        if not cfg.get("calendar"):
            continue
        for user, udata in sorted(acl.users.items()):
            if project in udata.get("grants", {}):
                targets.append((project, user))
    return targets


def sync_all_due(
    acl,
    token_store,
    *,
    registry: ConnectorRegistry | None = None,
    now: datetime | None = None,
    interval: timedelta = DEFAULT_SYNC_INTERVAL,
) -> int:
    """Sync every (project, user) target whose cache is missing or older
    than *interval*. Returns the number synced. A single target's failure
    (e.g. an unreadable vault path) is logged and skipped — never aborts
    the sweep, same isolation principle as busy_from_backend's per-source
    error handling."""
    now = now or datetime.now(timezone.utc)
    synced = 0
    for project, user in iter_calendar_targets(acl):
        try:
            cache = read_cache(acl, project, user)
            if not is_due(cache, now, interval):
                continue
            sync_user_calendar(acl, token_store, project, user, registry=registry, now=now)
            synced += 1
        except Exception:
            logger.warning("calendar sync failed for project=%r user=%r", project, user, exc_info=True)
    return synced


async def calendar_sync_loop(acl_fn, token_store_fn, *, tick_seconds: int = 60, now_fn=None) -> None:
    """Check every *tick_seconds* which (project, user) targets are due and
    sync them. A tick's exception never kills the loop (same contract as
    notify/scheduler.py's scheduler_loop)."""
    import asyncio

    while True:
        now = now_fn() if now_fn else datetime.now(timezone.utc)
        try:
            sync_all_due(acl_fn(), token_store_fn(), now=now)
        except Exception:
            logger.warning("calendar_sync_loop tick failed", exc_info=True)
        await asyncio.sleep(tick_seconds)
