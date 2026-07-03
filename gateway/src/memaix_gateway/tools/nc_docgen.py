# SPDX-License-Identifier: AGPL-3.0-or-later
"""nc_generate_report — render a pm_report() rollup as a .odt file, written
to the project's linked Nextcloud files (FEATURE-NEXTCLOUD-BACKEND.md §8,
Byggordning steg 7). Lowest-priority piece of the Nextcloud spec; kept to
exactly this one use case rather than a general document-template system.
"""

from __future__ import annotations

from ..acl import Acl
from ..nextcloud.docgen import pm_report_sections, render_odt
from .pm_engine import pm_report


def nc_generate_report(
    acl: Acl, user_id: str, project: str, path: str, kind: str = "status", audience: str = "team",
    scenario_id: int | None = None, period_start: str | None = None, period_end: str | None = None,
    *, _files, _pm,
) -> dict:
    """Generate a pm_report() rollup as a .odt file and write it to the
    project's linked Nextcloud files at `path`. Same kind/audience options
    as pm_report; requires collaborator (a files write), same bar as
    nc_files_write."""
    acl.enforce(user_id, project, "collaborator")
    report = pm_report(acl, user_id, project, kind, audience, scenario_id, period_start, period_end, _pm=_pm)
    sections = pm_report_sections(report)
    title = f"{project} — {kind} report ({audience})"
    odt_bytes = render_odt(title, sections)
    _files.write_binary(path, odt_bytes)
    return {"path": path, "bytes": len(odt_bytes), "kind": kind, "audience": audience}
