"""MCP server entrypoint — STUB.

SPDX-License-Identifier: AGPL-3.0-or-later

Implement against docs/BUILD.md. Responsibilities:
  - Start an MCP server with Streamable HTTP transport + OAuth 2.1 (PKCE, CIMD/DCR).
  - On each tool call: resolve OAuth subject -> user (Acl.user_by_subject),
    then Acl.enforce(user, project, need) BEFORE touching any backend.
  - Register tools from memaix_gateway.tools.* (email, calendar, files, memory, backlog, whoami).

This file intentionally contains no working server yet — see the build phases in BUILD.md.
"""

from __future__ import annotations

from . import config
from .acl import Acl


def build():
    cfg = config.load()
    acl = Acl.from_config(cfg["acl"])
    # TODO (BUILD.md phase 1+): construct MCP server, wire auth, register tools, enforce acl.
    return acl, cfg


def main() -> None:
    build()
    raise NotImplementedError("Gateway server not implemented yet — see docs/BUILD.md")


if __name__ == "__main__":
    main()
