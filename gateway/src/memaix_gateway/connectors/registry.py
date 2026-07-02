# SPDX-License-Identifier: AGPL-3.0-or-later
"""Connector registry — maps a project resource's `type` to an adapter
factory (FEATURE-CONNECTOR-FRAMEWORK.md §5).

Deliberate simplification vs. the design doc's illustrative factory
signature: factories here receive `(acl, project, user, resource_cfg,
token)` rather than a bare `resource_cfg` + resolved `secret`, because the
adapters being wrapped (`_make_mailbox`, `_RealDavAdapter`) already resolve
their own `*_ref` secrets from `resource_cfg` via `config.secret` — handing
them `acl`/`project` lets them do that themselves instead of duplicating
field-name knowledge in the registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

# Capability -> the type assumed when a project resource doesn't set `type`
# explicitly, preserving today's acl.yaml files (mailbox/calendar configs
# have never carried a `type` key — imap/caldav were always implied).
DEFAULT_TYPES: dict[str, str] = {
    "mail": "imap",
    "calendar": "caldav",
    "files": "local",
}

# Capability name -> the acl.yaml resource key it actually reads today.
# 'mail' and 'files' predate this framework under different resource names
# ('mailbox', 'vault'); keeping the capability name generic (matching the
# design doc) while mapping it to the real key avoids renaming every
# project's acl.yaml.
RESOURCE_KEYS: dict[str, str] = {
    "mail": "mailbox",
    "files": "vault",
}


class ConnectorAuthRequired(Exception):
    """Raised when an auth='per_user' connector has no linked account for this user."""

    def __init__(self, capability: str, type_: str) -> None:
        self.capability = capability
        self.type = type_
        super().__init__(f"auth_required: no {type_!r} account linked for capability {capability!r}")


@dataclass(frozen=True)
class ConnectorSpec:
    type: str
    capability: str            # 'mail' | 'calendar' | 'files' | 'contacts' | 'chat' | 'issues'
    auth: str                  # 'shared' | 'per_user'
    factory: Callable           # (acl, project, user, resource_cfg, token) -> adapter
    provider: str | None = None  # token_store provider name for auth='per_user'; defaults to `type`


class ConnectorRegistry:
    """type->factory lookup per capability. Empty until `register()`d."""

    def __init__(self) -> None:
        self._specs: dict[tuple[str, str], ConnectorSpec] = {}

    def register(self, *specs: ConnectorSpec) -> None:
        for spec in specs:
            self._specs[(spec.capability, spec.type)] = spec

    def get(self, acl, token_store, project: str, capability: str, user: str):
        """Resolve `acl.resource(project, capability)`'s `type` to a spec, resolve
        credentials per its `auth` mode, and build the adapter via its factory.

        Raises ValueError if the resource isn't configured or `type` is
        unregistered; ConnectorAuthRequired if auth='per_user' and the user
        has no linked account for it.
        """
        resource_cfg = acl.resource(project, RESOURCE_KEYS.get(capability, capability))
        if not resource_cfg:
            raise ValueError(f"project {project!r} has no {capability} configured")

        type_ = resource_cfg.get("type", DEFAULT_TYPES.get(capability, capability))
        spec = self._specs.get((capability, type_))
        if spec is None:
            raise ValueError(f"unknown connector type {type_!r} for capability {capability!r}")

        token = None
        if spec.auth == "per_user":
            provider = spec.provider or spec.type
            accounts = token_store.list_accounts(user)
            match = next((a for a in accounts if a["provider"] == provider), None)
            if match is None:
                raise ConnectorAuthRequired(capability, spec.type)
            token = token_store.load_one(user, provider, match["account"])
            if token is None:
                raise ConnectorAuthRequired(capability, spec.type)

        return spec.factory(acl, project, user, resource_cfg, token)


_registry: ConnectorRegistry | None = None


def default_registry() -> ConnectorRegistry:
    """Process-wide registry populated with the built-in catalog (lazy singleton,
    same pattern as outbox.queue.default_queue())."""
    global _registry
    if _registry is None:
        from .catalog import register_defaults

        _registry = ConnectorRegistry()
        register_defaults(_registry)
    return _registry
