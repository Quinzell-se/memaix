# SPDX-License-Identifier: AGPL-3.0-or-later
"""Built-in connector catalog — registers today's real adapters with the
registry (FEATURE-CONNECTOR-FRAMEWORK.md §6).

`mail`/`imap` and `calendar`/`caldav` wrap the pluggable adapters
tools/email.py (`_imap`) and tools/calendar.py (`_dav`) already had before
this framework existed. Cutting `email_*`/`calendar_*`'s actual call sites
over to `registry.get(...)` (replacing `_make_mailbox`/
`_resolve_calendar_dav`) is deferred follow-up work — see ROADMAP.md —
since `_resolve_calendar_dav` in particular has several working, tested
auth-priority branches (OAuth refresh, iCal, FreeBusy, static CalDAV) that
deserve their own focused migration rather than being bundled in here.

`contacts`/`carddav`, `files`/`webdav`, `tasks`/`caldav` and `deck`/
`nextcloud` are the Nextcloud adapters (FEATURE-NEXTCLOUD-BACKEND.md §4-5-7,
Byggordning steps 5-6) and are wired all the way to live MCP tools
(server.py's `contacts_search`/`contacts_get`, `nc_files_*`, `nc_tasks_*`,
`deck_sync`) since, unlike the local vault, they aren't replacing an
existing working code path — they're additional capability. `tasks` is a
resource key distinct from `calendar` even though both default to type
'caldav' — a VTODO task list and an event calendar are typically different
CalDAV collections.

`chat` has no adapter to wrap yet — it gets a registered spec once a real
backend exists (Nextcloud Talk).
"""

from __future__ import annotations

from .registry import ConnectorRegistry, ConnectorSpec


def _imap_factory(acl, project, user, resource_cfg, token):
    from ..tools.email import _make_mailbox

    return _make_mailbox(acl, project)


def _caldav_factory(acl, project, user, resource_cfg, token):
    from ..tools.calendar import _RealDavAdapter

    return _RealDavAdapter(acl, project)


def _carddav_factory(acl, project, user, resource_cfg, token):
    from .. import config
    from .adapters.contacts_carddav import CardDavContactsAdapter

    password = config.secret(resource_cfg.get("password_ref"))
    return CardDavContactsAdapter(resource_cfg["url"], resource_cfg.get("user", ""), password or "")


def _webdav_files_factory(acl, project, user, resource_cfg, token):
    from .. import config
    from .adapters.files_webdav import WebDavFilesAdapter

    password = config.secret(resource_cfg.get("password_ref"))
    return WebDavFilesAdapter(resource_cfg["url"], resource_cfg.get("user", ""), password or "")


def _tasks_caldav_factory(acl, project, user, resource_cfg, token):
    from .. import config
    from .adapters.tasks_caldav import CalDavTasksAdapter

    password = config.secret(resource_cfg.get("password_ref"))
    return CalDavTasksAdapter(resource_cfg["url"], resource_cfg.get("user", ""), password or "")


def _deck_factory(acl, project, user, resource_cfg, token):
    from .. import config
    from .adapters.deck_nextcloud import DeckAdapter

    password = config.secret(resource_cfg.get("password_ref"))
    return DeckAdapter(resource_cfg["url"], resource_cfg.get("user", ""), password or "")


def register_defaults(registry: ConnectorRegistry) -> None:
    registry.register(
        ConnectorSpec(type="imap", capability="mail", auth="shared", factory=_imap_factory),
        ConnectorSpec(type="caldav", capability="calendar", auth="shared", factory=_caldav_factory),
        ConnectorSpec(type="carddav", capability="contacts", auth="shared", factory=_carddav_factory),
        ConnectorSpec(type="webdav", capability="files", auth="shared", factory=_webdav_files_factory),
        ConnectorSpec(type="caldav", capability="tasks", auth="shared", factory=_tasks_caldav_factory),
        ConnectorSpec(type="nextcloud", capability="deck", auth="shared", factory=_deck_factory),
    )
