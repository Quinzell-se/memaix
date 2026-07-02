# SPDX-License-Identifier: AGPL-3.0-or-later
"""Notification channel adapters — email / webhook / ntfy.

See docs/FEATURE-PROACTIVE-BRIEF.md §4. Each channel's send() is called
independently by notify.deliver so one broken channel never blocks the others.
"""

from __future__ import annotations

import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class NotificationChannel(Protocol):
    def send(self, subject: str, markdown: str, text: str) -> None: ...


class EmailChannel:
    """Sends via a project's own mailbox/SMTP config (spec must include
    'project' — a brief spans multiple projects, so the sending identity is
    explicit rather than inferred)."""

    def __init__(self, acl, spec: dict, *, _smtp=None) -> None:
        self._acl = acl
        self._to = spec["to"]
        self._project = spec.get("project")
        self._smtp = _smtp

    def send(self, subject: str, markdown: str, text: str) -> None:
        cfg = self._acl.resource(self._project, "mailbox") if self._project else None
        if not cfg:
            raise ValueError(
                f"email channel needs a 'project' with a configured mailbox (got {self._project!r})"
            )
        import smtplib
        from email.message import EmailMessage

        msg = EmailMessage()
        msg["To"] = self._to
        msg["Subject"] = subject
        msg["From"] = cfg.get("user", "")
        msg.set_content(text)

        if self._smtp is not None:
            self._smtp.send_message(msg)
            return

        from .. import config as cfg_mod
        smtp_cfg: dict = self._acl.resource(self._project, "smtp") or {}
        host = smtp_cfg.get("host", cfg.get("host", "localhost"))
        port = int(smtp_cfg.get("port", 587))
        password = cfg_mod.secret(cfg.get("password_ref"))
        with smtplib.SMTP(host, port) as s:
            s.starttls()
            s.login(cfg.get("user", ""), password)
            s.send_message(msg)


class WebhookChannel:
    def __init__(self, url: str, fmt: str = "raw", *, _http=None) -> None:
        self._url = url
        self._fmt = fmt
        self._http = _http

    def send(self, subject: str, markdown: str, text: str) -> None:
        http = self._http
        if http is None:
            import requests
            http = requests
        payload = (
            {"text": f"*{subject}*\n{text}"} if self._fmt == "slack"
            else {"subject": subject, "text": text, "markdown": markdown}
        )
        resp = http.post(self._url, json=payload, timeout=10)
        raise_for_status = getattr(resp, "raise_for_status", None)
        if raise_for_status:
            raise_for_status()


class NtfyChannel:
    def __init__(self, topic: str, server: str = "https://ntfy.sh", *, _http=None) -> None:
        self._topic = topic
        self._server = server.rstrip("/")
        self._http = _http

    def send(self, subject: str, markdown: str, text: str) -> None:
        http = self._http
        if http is None:
            import requests
            http = requests
        url = f"{self._server}/{self._topic}"
        resp = http.post(url, data=text.encode("utf-8"), headers={"Title": subject}, timeout=10)
        raise_for_status = getattr(resp, "raise_for_status", None)
        if raise_for_status:
            raise_for_status()


def build_channels(specs: list[dict], *, acl=None, _http=None, _smtp=None) -> list[NotificationChannel]:
    """Build channel adapters from JSON specs, skipping (and logging) any
    that fail to construct — one bad spec must not disable the others."""
    from .. import config as cfg_mod

    channels: list[NotificationChannel] = []
    for spec in specs or []:
        ctype = spec.get("type")
        try:
            if ctype == "email":
                channels.append(EmailChannel(acl, spec, _smtp=_smtp))
            elif ctype == "webhook":
                url = spec.get("url") or cfg_mod.secret(spec.get("url_ref"))
                if not url:
                    raise ValueError("webhook channel needs 'url' or 'url_ref'")
                channels.append(WebhookChannel(url, spec.get("format", "raw"), _http=_http))
            elif ctype == "ntfy":
                channels.append(NtfyChannel(spec["topic"], spec.get("server", "https://ntfy.sh"), _http=_http))
            else:
                logger.warning("unknown notification channel type: %r", ctype)
        except Exception:
            logger.warning("failed to build notification channel %r", spec, exc_info=True)
    return channels
