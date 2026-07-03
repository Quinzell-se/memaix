# SPDX-License-Identifier: AGPL-3.0-or-later
"""contacts_* tools — address book lookup via the connector framework
(FEATURE-NEXTCLOUD-BACKEND.md §5).

The _contacts keyword argument accepts a connectors.base.ContactsBackend
duck type: search(query) -> list[dict], get(id) -> dict. Built by
server.py from acl.resource(project, "contacts") via the connector
registry — this module never talks to CardDAV directly.
"""

from __future__ import annotations

from ..acl import Acl


def contacts_search(acl: Acl, user_id: str, project: str, query: str, *, _contacts) -> list[dict]:
    """Search the project's linked address book by name/email/org/phone substring."""
    acl.enforce(user_id, project, "reader")
    return _contacts.search(query)


def contacts_get(acl: Acl, user_id: str, project: str, id: str, *, _contacts) -> dict:
    """Fetch one contact by id from the project's linked address book."""
    acl.enforce(user_id, project, "reader")
    return _contacts.get(id)
