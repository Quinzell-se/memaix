# SPDX-License-Identifier: AGPL-3.0-or-later
"""email_* tools — IMAP/SMTP with injected client for testability.

The *_imap / *_smtp keyword arguments accept duck-typed objects whose
interface is documented below.  When None, a real imap_tools.MailBox /
smtplib.SMTP connection is created from project config.

_imap duck type (must implement):
  fetch(criteria='ALL', *, mark_seen=False, limit=None) -> Iterable[msg]
    where msg has: uid, subject, from_, to, cc, date_str, seen, text, html
  folder.set(name: str)
  append(msg_bytes: bytes, flags: str, *, folder: str)
  logout()

_smtp duck type:
  send_message(msg: email.message.EmailMessage)

Feature gate:
  acl.resource(project, "allow_send") must be truthy to use email_send.

Outbox gate:
  email_send is outgoing and hard to undo, so it is also routed through the
  approval outbox (see outbox/policy.py). When action_mode() resolves to
  'review' (project's outbox=review, global default, or an unlisted
  recipient), the send is queued instead of executed and the call returns
  {"pending": True, "action_id": ...}. Passing _confirmed=True (used by
  outbox.execute after an operator approves) always executes immediately.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from .. import config
from ..acl import Acl

# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _mailbox_cfg(acl: Acl, project: str) -> dict:
    cfg = acl.resource(project, "mailbox")
    if not cfg:
        raise ValueError(f"project {project!r} has no mailbox configured")
    return cfg


def _make_mailbox(acl: Acl, project: str):
    from imap_tools import MailBox

    cfg = _mailbox_cfg(acl, project)
    password = config.secret(cfg.get("password_ref"))
    if password is None:
        raise ValueError(f"no password configured for mailbox (project {project!r})")
    mb = MailBox(cfg["host"])
    mb.login(cfg["user"], password)
    return mb


def _imap_quote(value: str) -> str:
    """Escape a string for safe use inside an IMAP quoted-string.

    Within IMAP quoted-strings the backslash and double-quote are the only
    characters that must be escaped; CR/LF are stripped since they can never
    appear in a quoted-string and would otherwise allow command injection.
    """
    value = value.replace("\r", " ").replace("\n", " ")
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _msg_to_dict(m, full: bool = False) -> dict:
    base: dict = {
        "id": str(m.uid),
        "subject": m.subject,
        "from": m.from_,
        "date": m.date_str,
        "seen": m.seen,
    }
    if full:
        base.update(
            {
                "to": list(m.to) if m.to else [],
                "cc": list(m.cc) if m.cc else [],
                "body": m.text or m.html or "",
            }
        )
    return base


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


def email_list(
    acl: Acl,
    user_id: str,
    project: str,
    folder: str = "INBOX",
    limit: int = 20,
    *,
    _imap=None,
) -> list[dict]:
    """List recent messages.  Returns [{id, subject, from, date, seen}]."""
    acl.enforce(user_id, project, "collaborator")
    mb = _imap if _imap is not None else _make_mailbox(acl, project)
    mb.folder.set(folder)
    msgs = list(mb.fetch("ALL", mark_seen=False, limit=limit))
    return [_msg_to_dict(m) for m in msgs]


def email_read(
    acl: Acl,
    user_id: str,
    project: str,
    id: str,
    *,
    _imap=None,
) -> dict:
    """Fetch a single message by UID.  Returns full message dict."""
    acl.enforce(user_id, project, "collaborator")
    mb = _imap if _imap is not None else _make_mailbox(acl, project)
    msgs = list(mb.fetch(f"UID {id}", mark_seen=True))
    if not msgs:
        raise FileNotFoundError(f"message not found: {id!r}")
    return _msg_to_dict(msgs[0], full=True)


def email_search(
    acl: Acl,
    user_id: str,
    project: str,
    query: str,
    limit: int = 20,
    *,
    _imap=None,
) -> list[dict]:
    """IMAP BODY search.  Returns [{id, subject, from, date}]."""
    acl.enforce(user_id, project, "collaborator")
    mb = _imap if _imap is not None else _make_mailbox(acl, project)
    msgs = list(mb.fetch(f'BODY "{_imap_quote(query)}"', mark_seen=False, limit=limit))
    return [_msg_to_dict(m) for m in msgs]


def email_create_draft(
    acl: Acl,
    user_id: str,
    project: str,
    to: str,
    subject: str,
    body: str,
    cc: str | None = None,
    in_reply_to: str | None = None,
    *,
    _imap=None,
) -> dict:
    """IMAP APPEND to Drafts folder.  Returns {status, subject}."""
    acl.enforce(user_id, project, "collaborator")
    cfg = _mailbox_cfg(acl, project)
    mb = _imap if _imap is not None else _make_mailbox(acl, project)

    msg = EmailMessage()
    msg["To"] = to
    msg["Subject"] = subject
    msg["From"] = cfg.get("user", "")
    if cc:
        msg["Cc"] = cc
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    msg.set_content(body)
    mb.append(msg.as_bytes(), "\\Draft", folder="Drafts")
    return {"status": "draft_created", "subject": subject}


def email_send(
    acl: Acl,
    user_id: str,
    project: str,
    to: str,
    subject: str,
    body: str,
    cc: str | None = None,
    *,
    _smtp=None,
    _confirmed: bool = False,
    _outbox=None,
    _cfg: dict | None = None,
) -> dict:
    """Send a message via SMTP.  Requires owner + allow_send feature flag.

    Queued for approval instead of sent when the outbox policy resolves to
    'review' (see module docstring) — unless _confirmed=True.
    """
    acl.enforce(user_id, project, "owner")
    # Feature gate
    if not acl.resource(project, "allow_send"):
        raise RuntimeError("feature_disabled: allow_send is false")

    if not _confirmed:
        from ..outbox.policy import action_mode
        from ..outbox.preview import render_preview
        from ..outbox.queue import default_queue

        args = {"to": to, "subject": subject, "body": body, "cc": cc}
        memaix_cfg = _cfg if _cfg is not None else config.load()
        if action_mode(memaix_cfg, acl, project, "email_send", args) == "review":
            queue = _outbox if _outbox is not None else default_queue()
            action_id = queue.enqueue(
                user_id, project, "email_send", args, render_preview("email_send", args)
            )
            return {
                "pending": True,
                "action_id": action_id,
                "note": "Väntar på godkännande i utkorgen",
            }

    cfg = _mailbox_cfg(acl, project)
    smtp_cfg: dict = acl.resource(project, "smtp") or {}

    msg = EmailMessage()
    msg["To"] = to
    msg["Subject"] = subject
    msg["From"] = cfg.get("user", "")
    if cc:
        msg["Cc"] = cc
    msg.set_content(body)

    if _smtp is not None:
        _smtp.send_message(msg)
    else:
        host = smtp_cfg.get("host", cfg.get("host", "localhost"))
        port = int(smtp_cfg.get("port", 587))
        user = cfg.get("user", "")
        password = config.secret(cfg.get("password_ref"))
        if password is None:
            raise ValueError(f"no password configured for mailbox (project {project!r})")
        with smtplib.SMTP(host, port) as s:
            s.starttls()
            s.login(user, password)
            s.send_message(msg)

    return {"status": "sent", "to": to, "subject": subject}
