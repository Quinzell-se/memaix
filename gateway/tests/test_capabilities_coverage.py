# SPDX-License-Identifier: AGPL-3.0-or-later
"""Anti-drift test: every MCP tool must be discoverable or explicitly internal.

This is the mechanism that keeps docs/FEATURE-DISCOVERABILITY.md's promise —
a new tool added to server.py without registering a Capability (or marking it
INTERNAL_TOOLS) fails CI here instead of silently becoming undiscoverable.
"""

from __future__ import annotations

import pytest

from memaix_gateway import server
from memaix_gateway.capabilities import catalog
from memaix_gateway.capabilities.registry import all_capabilities, clear_registry
from memaix_gateway.i18n import _load as load_locale


@pytest.fixture()
def full_catalog():
    """Registry populated with the real catalog, regardless of test order/state.

    register_defaults() is idempotent by key, so calling it after a clear
    always restores the exact same set — this test does not depend on
    whether some other test file cleared the module-level registry first.
    """
    clear_registry()
    catalog.register_defaults()
    yield
    # Restore rather than leave empty — other test modules (and server.py
    # itself) assume the registry reflects the real catalog once populated.
    clear_registry()
    catalog.register_defaults()


def test_every_tool_is_covered_or_internal(full_catalog):
    tool_names = server.all_tool_names()
    covered: set[str] = set()
    for cap in all_capabilities():
        covered.update(cap.tools)

    uncovered = tool_names - covered - catalog.INTERNAL_TOOLS
    assert not uncovered, (
        f"Tools not discoverable and not marked internal: {sorted(uncovered)}. "
        "Register a Capability in capabilities/catalog.py or add to INTERNAL_TOOLS."
    )


def test_no_capability_references_a_nonexistent_tool(full_catalog):
    tool_names = server.all_tool_names()
    for cap in all_capabilities():
        unknown = set(cap.tools) - tool_names
        assert not unknown, f"Capability {cap.key!r} references unknown tools: {unknown}"


def test_internal_tools_do_not_overlap_registered_capabilities(full_catalog):
    covered: set[str] = set()
    for cap in all_capabilities():
        covered.update(cap.tools)
    overlap = covered & catalog.INTERNAL_TOOLS
    assert not overlap, f"Tools both registered and marked internal: {overlap}"


def test_every_capability_has_english_i18n_strings(full_catalog):
    en = load_locale("en")
    missing = []
    for cap in all_capabilities():
        for key in (cap.title_key, cap.summary_key, cap.example_prompts_key):
            if key not in en:
                missing.append(key)
    assert not missing, f"Missing en.json keys: {missing}"
