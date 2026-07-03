# SPDX-License-Identifier: AGPL-3.0-or-later
"""nc_tasks_* tools — Nextcloud (CalDAV VTODO) task lists via the connector
framework (FEATURE-NEXTCLOUD-BACKEND.md §3, Byggordning step 5).

`_tasks` accepts a connectors.base.TasksBackend duck type, built by
server.py via the connector registry.
"""

from __future__ import annotations

from ..acl import Acl


def nc_tasks_list(acl: Acl, user_id: str, project: str, *, _tasks) -> list[dict]:
    acl.enforce(user_id, project, "reader")
    return _tasks.list()


def nc_tasks_add(
    acl: Acl, user_id: str, project: str, title: str, due: str | None = None, notes: str | None = None, *, _tasks,
) -> dict:
    acl.enforce(user_id, project, "collaborator")
    return _tasks.add(title, due, notes)


def nc_tasks_complete(acl: Acl, user_id: str, project: str, id: str, *, _tasks) -> dict:
    acl.enforce(user_id, project, "collaborator")
    return _tasks.complete(id)
