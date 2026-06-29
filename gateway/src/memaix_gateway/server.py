# SPDX-License-Identifier: AGPL-3.0-or-later
"""MCP server entrypoint — Fas 1: stdio transport, local-vault files, whoami.

User identity in Fas 1 comes from MEMAIX_USER env var (no OAuth yet).
Fas 4 will swap in Hydra token validation (see docs/BUILD.md).
"""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from . import config
from .acl import Acl
from .tools import files as t_files
from .tools import whoami as t_whoami

_acl: Acl | None = None


def _get_acl() -> Acl:
    global _acl
    if _acl is None:
        cfg = config.load()
        _acl = Acl.from_config(cfg["acl"])
    return _acl


def _user() -> str:
    uid = os.environ.get("MEMAIX_USER", "").strip()
    if not uid:
        raise RuntimeError("MEMAIX_USER is not set — cannot identify caller")
    return uid


mcp = FastMCP("memaix")


@mcp.tool()
def whoami() -> dict:
    """Return the calling user's identity and project grants."""
    return t_whoami.whoami(_get_acl(), _user())


@mcp.tool()
def files_list(project: str, path: str = "/") -> list:
    """List files and directories in a project vault path."""
    return t_files.list_files(_get_acl(), _user(), project, path)


@mcp.tool()
def files_read(project: str, path: str) -> str:
    """Read a file from a project vault."""
    return t_files.read_file(_get_acl(), _user(), project, path)


@mcp.tool()
def files_write(project: str, path: str, content: str) -> str:
    """Write a file to a project vault."""
    return t_files.write_file(_get_acl(), _user(), project, path, content)


@mcp.tool()
def files_search(project: str, query: str, path: str = "/") -> list:
    """Search file contents in a project vault."""
    return t_files.search_files(_get_acl(), _user(), project, query, path)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
