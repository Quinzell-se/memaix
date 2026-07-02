# SPDX-License-Identifier: AGPL-3.0-or-later
"""SSRF guard for user-supplied outbound URLs.

Some tools accept a URL from an authenticated user (or an agent acting as
them) that the server then fetches/posts to: an iCal secret URL
(calendar_setup) and notification channel webhook/ntfy URLs
(brief_configure). Without a guard, a user — or a prompt-injected agent —
can point those at internal targets (cloud metadata at 169.254.169.254,
localhost services, RFC1918 hosts) and turn the gateway into a confused
deputy (SSRF).

validate_external_url() rejects anything that isn't a plain http(s) URL to a
publicly-routable host. It's applied twice on purpose: at configuration time
(fast, clear rejection when the user sets the URL) and again immediately
before the actual request in the adapter (authoritative — narrows the
DNS-rebinding TOCTOU window, since a name that resolved public at set-time
could later resolve to a private IP). The residual rebind race between this
check and connect() is documented, not eliminated; fully closing it would
require pinning the resolved IP into the socket, which the stdlib HTTP
clients don't expose cleanly.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class BlockedURLError(ValueError):
    """Raised when a user-supplied URL targets a non-public / disallowed host."""


def _is_blocked_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True  # unparseable → block
    return (
        addr.is_loopback
        or addr.is_private
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def validate_external_url(url: str, *, resolve: bool = True) -> str:
    """Return the URL unchanged if it's a safe external http(s) target, else
    raise BlockedURLError.

    resolve=True (the fetch-time check) additionally resolves the hostname
    and blocks if ANY resolved address is non-public. resolve=False
    (config-time) skips DNS and only validates scheme/host shape — so setting
    a URL doesn't depend on the name resolving right then.
    """
    if not url or not isinstance(url, str):
        raise BlockedURLError("empty or non-string URL")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise BlockedURLError(f"URL scheme must be http/https, got {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise BlockedURLError("URL has no host")

    # A literal IP in the URL is checked directly (no DNS needed). Parse in a
    # try (ValueError = "not a literal IP, it's a hostname"), but do the
    # block decision OUTSIDE the try — BlockedURLError subclasses ValueError,
    # so raising it inside would be swallowed by our own except.
    is_literal_ip = False
    try:
        ipaddress.ip_address(host)
        is_literal_ip = True
    except ValueError:
        pass
    if is_literal_ip:
        if _is_blocked_ip(host):
            raise BlockedURLError(f"URL host is a non-public address: {host}")
        return url

    if resolve:
        try:
            infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
        except socket.gaierror as exc:
            raise BlockedURLError(f"could not resolve host {host!r}: {exc}") from exc
        for info in infos:
            ip = str(info[4][0])
            if _is_blocked_ip(ip):
                raise BlockedURLError(f"URL host {host!r} resolves to a non-public address: {ip}")
    return url
