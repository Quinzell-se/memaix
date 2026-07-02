# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for safety.net.validate_external_url — the SSRF guard on
user-supplied outbound URLs (iCal secret URL, notification channel URLs)."""

from __future__ import annotations

import pytest

from memaix_gateway.safety.net import BlockedURLError, validate_external_url


@pytest.mark.parametrize("url", [
    "http://169.254.169.254/latest/meta-data/",   # cloud metadata (link-local)
    "http://127.0.0.1:6379/",                       # loopback
    "http://10.0.0.5/",                             # private
    "http://192.168.1.1/",                          # private
    "http://172.16.0.1/",                           # private
    "http://[::1]/",                                # ipv6 loopback
    "http://0.0.0.0/",                              # unspecified
])
def test_blocks_internal_literal_ips_even_without_resolve(url):
    # A literal IP is checked directly, no DNS needed — blocked even at config-time.
    with pytest.raises(BlockedURLError):
        validate_external_url(url, resolve=False)


@pytest.mark.parametrize("url", [
    "ftp://example.com/x",
    "file:///etc/passwd",
    "gopher://example.com",
    "",
])
def test_blocks_non_http_schemes_and_empty(url):
    with pytest.raises(BlockedURLError):
        validate_external_url(url, resolve=False)


def test_allows_public_literal_ip():
    assert validate_external_url("http://8.8.8.8/", resolve=False) == "http://8.8.8.8/"


def test_allows_public_hostname_without_resolve():
    # resolve=False skips DNS — config-time acceptance doesn't depend on the
    # name resolving at that instant.
    assert validate_external_url("https://hooks.example.com/abc", resolve=False)


def test_resolve_blocks_name_pointing_at_loopback(monkeypatch):
    import memaix_gateway.safety.net as net

    def fake_getaddrinfo(host, port):
        return [(0, 0, 0, "", ("127.0.0.1", port))]

    monkeypatch.setattr(net.socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(BlockedURLError):
        validate_external_url("https://sneaky.example.com/x", resolve=True)


def test_resolve_allows_name_pointing_at_public(monkeypatch):
    import memaix_gateway.safety.net as net

    def fake_getaddrinfo(host, port):
        return [(0, 0, 0, "", ("93.184.216.34", port))]

    monkeypatch.setattr(net.socket, "getaddrinfo", fake_getaddrinfo)
    assert validate_external_url("https://example.com/x", resolve=True)
