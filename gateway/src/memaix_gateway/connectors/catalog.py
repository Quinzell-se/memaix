# SPDX-License-Identifier: AGPL-3.0-or-later
"""Built-in connector catalog — registers today's real adapters with the
registry (FEATURE-CONNECTOR-FRAMEWORK.md §6).

Scope note: only `mail`/`imap` and `calendar`/`caldav` are registered here,
because those are the two capabilities that already have a real, pluggable
adapter behind an injectable duck type in tools/email.py (`_imap`) and
tools/calendar.py (`_dav`). Cutting `email_*`/`calendar_*`'s actual call
sites over to `registry.get(...)` (replacing `_make_mailbox`/
`_resolve_calendar_dav`) is deferred follow-up work — see ROADMAP.md — since
`_resolve_calendar_dav` in particular has several working, tested auth-
priority branches (OAuth refresh, iCal, FreeBusy, static CalDAV) that
deserve their own focused migration rather than being bundled in here.
`files`/`contacts`/`chat`/`issues` have no adapter to wrap yet at all
(tools/files.py is local-only, with no injectable backend) — they get a
registered spec once a real second backend exists for them (Nextcloud,
FEATURE-NEXTCLOUD-BACKEND.md).
"""

from __future__ import annotations

from .registry import ConnectorRegistry, ConnectorSpec


def _imap_factory(acl, project, user, resource_cfg, token):
    from ..tools.email import _make_mailbox

    return _make_mailbox(acl, project)


def _caldav_factory(acl, project, user, resource_cfg, token):
    from ..tools.calendar import _RealDavAdapter

    return _RealDavAdapter(acl, project)


def register_defaults(registry: ConnectorRegistry) -> None:
    registry.register(
        ConnectorSpec(type="imap", capability="mail", auth="shared", factory=_imap_factory),
        ConnectorSpec(type="caldav", capability="calendar", auth="shared", factory=_caldav_factory),
    )
