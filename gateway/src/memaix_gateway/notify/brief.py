# SPDX-License-Identifier: AGPL-3.0-or-later
"""BriefBuilder — compose the daily brief content from injected tool functions.

See docs/FEATURE-PROACTIVE-BRIEF.md §5. Deliberately has zero imports of
server.py or tools.* at module scope — the caller (server.py, or a test)
supplies concrete functions via `tools`, so this stays a pure, fast-testable
function with no request/session context requirement (it must be callable
from the scheduler, outside any MCP request).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _tz_or_utc(tz_name: str):
    from zoneinfo import ZoneInfo
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return timezone.utc


def _day_bounds(now: datetime, tz_name: str) -> tuple[datetime, datetime]:
    tz = _tz_or_utc(tz_name)
    local_now = now.astimezone(tz)
    start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def _fmt_event_time(start: str, tz_name: str) -> str:
    """Calendar sources return 'start' as an ISO datetime (usually UTC) or a
    bare date for all-day events. Render it in the recipient's timezone so
    the brief matches their wall clock, not the source's."""
    if not start:
        return ""
    if len(start) <= 10:  # date-only — all-day event, nothing to convert
        return start
    try:
        dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
    except ValueError:
        return start
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_tz_or_utc(tz_name)).strftime("%H:%M")


def build(
    acl, user: str, cfg: dict | None, prefs: dict, *,
    now: datetime, tools: dict | None = None, last_run_iso: str | None = None,
) -> dict:
    """Return {"subject", "markdown", "text", "empty": bool}.

    tools (all optional; a missing/None entry silently skips that section):
      calendar_events(acl, user, project, day_start, day_end) -> list[{"title","start",...}]
      email_list(acl, user, project, folder, limit) -> list[{"subject","from","seen",...}]
      backlog_list(acl, user, project) -> list[{"id","title","status","updated_at",...}]
      pm_raid_list(acl, user, project) -> {"entries": [{"status": "open"/...}]}
    """
    tools = tools or {}
    projects = prefs.get("projects") or acl.visible_projects(user)
    tz_name = prefs.get("timezone", "UTC")
    day_start, day_end = _day_bounds(now, tz_name)

    brief_cfg = ((cfg or {}).get("memaix", {}) or {}).get("brief", {})
    max_mail = brief_cfg.get("max_mail", 5)
    mail_days = brief_cfg.get("mail_days", 3)
    send_when_empty = brief_cfg.get("send_when_empty", True)

    calendar_events_fn = tools.get("calendar_events")
    email_list_fn = tools.get("email_list")
    backlog_list_fn = tools.get("backlog_list")
    pm_raid_list_fn = tools.get("pm_raid_list")
    mail_triage_fn = tools.get("mail_triage")

    calendar_lines: list[str] = []
    mail_lines: list[str] = []
    backlog_lines: list[str] = []
    raid_open = 0

    for project in projects:
        if calendar_events_fn and acl.resource(project, "calendar"):
            try:
                for ev in (calendar_events_fn(acl, user, project, day_start, day_end) or []):
                    when = _fmt_event_time(ev.get('start', ''), tz_name)
                    calendar_lines.append(f"- [{project}] {ev.get('title', '(ingen titel)')} — {when}")
            except Exception:
                pass

        if email_list_fn and (acl.resource(project, "mailbox") or acl.resource(project, "email")):
            try:
                msgs = email_list_fn(acl, user, project, "INBOX", max_mail, days=mail_days) or []
                if mail_triage_fn and msgs:
                    msgs = mail_triage_fn(msgs) or msgs
                priority_icons = {"Hög": "🔴", "Medel": "🟡", "Låg": "⚪"}
                for m in msgs[:max_mail]:
                    icon = priority_icons.get(m.get("priority", ""), "•")
                    subject = m.get("subject", "(inget ämne)")
                    sender = m.get("from", "")
                    summary = m.get("summary", "")
                    inbox = m.get("inbox", "")
                    account_tag = f" [{inbox}]" if inbox else ""
                    line = f"- [{project}]{account_tag} {icon} {subject} — {sender}"
                    if summary:
                        line += f"\n  {summary}"
                    mail_lines.append(line)
            except Exception:
                pass

        if backlog_list_fn and acl.resource(project, "vault"):
            try:
                items = backlog_list_fn(acl, user, project) or []
                changed = (
                    [i for i in items if str(i.get("updated_at", "")) > last_run_iso]
                    if last_run_iso else []
                )
                for i in changed[:10]:
                    backlog_lines.append(
                        f"- [{project}] {i.get('id', '?')} — {i.get('title', '')} ({i.get('status', '')})"
                    )
            except Exception:
                pass

        if pm_raid_list_fn and acl.resource(project, "vault"):
            try:
                raid = pm_raid_list_fn(acl, user, project)
                entries = raid.get("entries", []) if isinstance(raid, dict) else []
                raid_open += sum(1 for e in entries if e.get("status") == "open")
            except Exception:
                pass

    has_content = bool(calendar_lines or mail_lines or backlog_lines or raid_open)
    if not has_content and not send_when_empty:
        return {"subject": "", "markdown": "", "text": "", "empty": True}

    today_str = now.astimezone(_tz_or_utc(tz_name)).strftime("%Y-%m-%d")
    subject = f"Memaix — din brief {today_str}"

    sections = [
        f"# Din brief — {today_str}",
        "## Kalender idag\n" + ("\n".join(calendar_lines) if calendar_lines else "_Inget planerat._"),
        "## Mail som väntar\n" + ("\n".join(mail_lines) if mail_lines else "_Inget nytt._"),
        "## Backlog-ändringar\n" + ("\n".join(backlog_lines) if backlog_lines else "_Inga ändringar sedan senast._"),
        f"## Öppna RAID-poster\n{raid_open}",
    ]
    markdown = "\n\n".join(sections)
    text = markdown.replace("# ", "").replace("## ", "").replace("_", "")

    return {"subject": subject, "markdown": markdown, "text": text, "empty": not has_content}
