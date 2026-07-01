# SPDX-License-Identifier: AGPL-3.0-or-later
"""Capability catalog — registers today's MCP tools with the registry.

Import this module once at process startup (server.py does it) so the
registry is populated before any capability lookup happens. Every new tool
added to server.py must either get a Capability here or be added to
INTERNAL_TOOLS — enforced by tests/test_capabilities_coverage.py.
"""

from __future__ import annotations

from .registry import Capability, register

# Tools that are plumbing, not a user-facing "job to be done" on their own.
# whoami/onboarding_complete are identity/setup mechanics; account_* are
# covered contextually by calendar_setup's auth_required flow rather than as
# a standalone capability (see docs/FEATURE-DISCOVERABILITY.md §9).
INTERNAL_TOOLS: frozenset[str] = frozenset(
    {"whoami", "onboarding_complete", "account_link", "account_list", "account_unlink"}
)


def register_defaults() -> None:
    register(
        # ------------------------------------------------------------------
        # memory
        # ------------------------------------------------------------------
        Capability(
            key="memory.remember", area="memory",
            title_key="cap.memory.remember.title",
            summary_key="cap.memory.remember.summary",
            tools=("memory_write", "memory_append"),
            example_prompts_key="cap.memory.remember.examples",
            needs_role="collaborator", needs_resource="vault",
            tags=("minne", "anteckning", "memory", "note"),
        ),
        Capability(
            key="memory.recall", area="memory",
            title_key="cap.memory.recall.title",
            summary_key="cap.memory.recall.summary",
            tools=("memory_read", "memory_search", "memory_history"),
            example_prompts_key="cap.memory.recall.examples",
            needs_role="reader", needs_resource="vault",
            tags=("minne", "sök", "memory", "search"),
        ),
        Capability(
            key="memory.undo", area="memory",
            title_key="cap.memory.undo.title",
            summary_key="cap.memory.undo.summary",
            tools=("memory_revert",),
            example_prompts_key="cap.memory.undo.examples",
            needs_role="collaborator", needs_resource="vault",
            tags=("ångra", "undo"),
        ),
        # ------------------------------------------------------------------
        # mail
        # ------------------------------------------------------------------
        Capability(
            key="mail.triage", area="mail",
            title_key="cap.mail.triage.title",
            summary_key="cap.mail.triage.summary",
            tools=("email_list", "email_search", "email_read"),
            example_prompts_key="cap.mail.triage.examples",
            needs_role="collaborator", needs_resource="mailbox",
            tags=("mejl", "inkorg", "mail", "inbox"),
        ),
        Capability(
            key="mail.draft", area="mail",
            title_key="cap.mail.draft.title",
            summary_key="cap.mail.draft.summary",
            tools=("email_create_draft",),
            example_prompts_key="cap.mail.draft.examples",
            needs_role="collaborator", needs_resource="mailbox",
            tags=("mejl", "utkast", "draft"),
        ),
        Capability(
            key="mail.send", area="mail",
            title_key="cap.mail.send.title",
            summary_key="cap.mail.send.summary",
            tools=("email_send",),
            example_prompts_key="cap.mail.send.examples",
            needs_role="owner", needs_resource="mailbox",
            tags=("mejl", "skicka", "send"),
        ),
        # ------------------------------------------------------------------
        # calendar
        # ------------------------------------------------------------------
        Capability(
            key="calendar.view", area="calendar",
            title_key="cap.calendar.view.title",
            summary_key="cap.calendar.view.summary",
            tools=("calendar_list", "calendar_find_free"),
            example_prompts_key="cap.calendar.view.examples",
            needs_role="collaborator", needs_resource="calendar",
            tags=("kalender", "möte", "calendar", "meeting"),
        ),
        Capability(
            key="calendar.manage", area="calendar",
            title_key="cap.calendar.manage.title",
            summary_key="cap.calendar.manage.summary",
            tools=("calendar_create", "calendar_update"),
            example_prompts_key="cap.calendar.manage.examples",
            needs_role="collaborator", needs_resource="calendar",
            tags=("kalender", "boka", "calendar", "book"),
        ),
        Capability(
            key="calendar.connect", area="calendar",
            title_key="cap.calendar.connect.title",
            summary_key="cap.calendar.connect.summary",
            tools=("calendar_setup", "calendar_status"),
            example_prompts_key="cap.calendar.connect.examples",
            needs_role="reader", needs_resource=None,
            tags=("kalender", "koppla", "connect"),
        ),
        # ------------------------------------------------------------------
        # files
        # ------------------------------------------------------------------
        Capability(
            key="files.manage", area="pm",  # grouped visually with project work
            title_key="cap.files.manage.title",
            summary_key="cap.files.manage.summary",
            tools=("files_list", "files_read", "files_search", "files_write"),
            example_prompts_key="cap.files.manage.examples",
            needs_role="collaborator", needs_resource="vault",
            tags=("filer", "dokument", "files", "documents"),
        ),
        # ------------------------------------------------------------------
        # backlog
        # ------------------------------------------------------------------
        Capability(
            key="backlog.capture", area="backlog",
            title_key="cap.backlog.capture.title",
            summary_key="cap.backlog.capture.summary",
            tools=("backlog_add",),
            example_prompts_key="cap.backlog.capture.examples",
            needs_role="collaborator", needs_resource="vault",
            tags=("backlog", "idé", "idea"),
        ),
        Capability(
            key="backlog.review", area="backlog",
            title_key="cap.backlog.review.title",
            summary_key="cap.backlog.review.summary",
            tools=("backlog_list", "backlog_get"),
            example_prompts_key="cap.backlog.review.examples",
            needs_role="reader", needs_resource="vault",
            tags=("backlog", "lista", "list"),
        ),
        Capability(
            key="backlog.score", area="backlog",
            title_key="cap.backlog.score.title",
            summary_key="cap.backlog.score.summary",
            tools=("backlog_score", "backlog_comment"),
            example_prompts_key="cap.backlog.score.examples",
            needs_role="collaborator", needs_resource="vault",
            tags=("backlog", "prioritera", "prioritize"),
        ),
        Capability(
            key="backlog.decide", area="backlog",
            title_key="cap.backlog.decide.title",
            summary_key="cap.backlog.decide.summary",
            tools=("backlog_set_status",),
            example_prompts_key="cap.backlog.decide.examples",
            needs_role="owner", needs_resource="vault",
            tags=("backlog", "godkänn", "approve"),
        ),
        # ------------------------------------------------------------------
        # pm
        # ------------------------------------------------------------------
        Capability(
            key="pm.methodology", area="pm",
            title_key="cap.pm.methodology.title",
            summary_key="cap.pm.methodology.summary",
            tools=("pm_set_methodology",),
            example_prompts_key="cap.pm.methodology.examples",
            needs_role="owner", needs_resource="vault",
            tags=("pm", "metodik", "methodology"),
        ),
        Capability(
            key="pm.sprint_plan", area="pm",
            title_key="cap.pm.sprint_plan.title",
            summary_key="cap.pm.sprint_plan.summary",
            tools=("pm_plan_sprint",),
            example_prompts_key="cap.pm.sprint_plan.examples",
            needs_role="owner", needs_resource="vault",
            tags=("pm", "sprint", "planera", "plan"),
        ),
        Capability(
            key="pm.sprint_status", area="pm",
            title_key="cap.pm.sprint_status.title",
            summary_key="cap.pm.sprint_status.summary",
            tools=("pm_sprint_status",),
            example_prompts_key="cap.pm.sprint_status.examples",
            needs_role="reader", needs_resource="vault",
            tags=("pm", "sprint", "status", "burndown"),
        ),
        Capability(
            key="pm.raid_add", area="pm",
            title_key="cap.pm.raid_add.title",
            summary_key="cap.pm.raid_add.summary",
            tools=("pm_raid_add",),
            example_prompts_key="cap.pm.raid_add.examples",
            needs_role="collaborator", needs_resource="vault",
            tags=("pm", "risk", "raid"),
        ),
        Capability(
            key="pm.raid_view", area="pm",
            title_key="cap.pm.raid_view.title",
            summary_key="cap.pm.raid_view.summary",
            tools=("pm_raid_list",),
            example_prompts_key="cap.pm.raid_view.examples",
            needs_role="reader", needs_resource="vault",
            tags=("pm", "risk", "raid"),
        ),
        Capability(
            key="pm.report", area="pm",
            title_key="cap.pm.report.title",
            summary_key="cap.pm.report.summary",
            tools=("pm_status_report",),
            example_prompts_key="cap.pm.report.examples",
            needs_role="reader", needs_resource="vault",
            tags=("pm", "rapport", "report", "status"),
        ),
        # ------------------------------------------------------------------
        # outbox (FEATURE-APPROVAL-OUTBOX.md)
        # ------------------------------------------------------------------
        Capability(
            key="outbox.review", area="outbox",
            title_key="cap.outbox.review.title",
            summary_key="cap.outbox.review.summary",
            tools=("outbox_list", "outbox_get", "outbox_approve", "outbox_reject"),
            example_prompts_key="cap.outbox.review.examples",
            needs_role="reader", needs_resource="vault",
            tags=("utkorg", "godkänn", "outbox", "approve"),
        ),
    )
