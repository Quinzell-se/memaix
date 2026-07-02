# SPDX-License-Identifier: AGPL-3.0-or-later
"""Deck ↔ backlog two-way sync (FEATURE-NEXTCLOUD-BACKEND.md §7, Byggordning
step 6).

Link: a backlog item that's paired with a Deck card carries
`deck_board_id`/`deck_stack_id`/`deck_card_id`/`deck_synced_at` in its
frontmatter. `deck_synced_at` is the baseline for conflict detection: on
each `deck_sync()` call, a side counts as "changed" if its own last-modified
timestamp is newer than that baseline.

  - only Deck changed  -> backlog item updated from the card
  - only backlog changed -> card updated from the backlog item
  - both changed        -> conflict; whichever is more recently modified
                            wins, and the conflict is reported (never
                            silently dropped) — "senast ändrad vinner"
  - neither changed      -> no-op

v1 scope, stated rather than hidden: only `title` (backlog frontmatter) and
`description` (backlog body / Deck description) are synced. Labels,
due dates, assignees and attachments are not — a documented limitation, not
an oversight. A card deleted on the Deck side is never used to delete the
backlog item (sync is additive/safe by default); it's just skipped.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .. import frontmatter as fm
from ..acl import Acl
from ..tools import backlog as t_backlog


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_ts(value) -> float:
    if not value:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return 0.0


def _backlog_dir(acl: Acl, project: str) -> Path:
    vault = acl.resource(project, "vault")
    if not vault:
        raise ValueError(f"project {project!r} has no vault configured")
    return Path(vault) / "backlog"


def _stamp(path: Path, *, description: str | None = None, **fields) -> None:
    meta, body = fm.split(path.read_text(encoding="utf-8"))
    if description is not None:
        body = description
    meta.update(fields)
    fm.write_atomic(path, fm.join(meta, body))


def _apply_deck_to_backlog(path: Path, card: dict) -> None:
    _stamp(path, title=card["title"], description=card["description"], updated_at=_now_iso(), deck_synced_at=_now_iso())


def _apply_backlog_to_deck(deck, board_id, stack_id, card_id: int, item: dict, path: Path) -> None:
    deck.update_card(board_id, stack_id, card_id, title=item["title"], description=item.get("description", ""))
    _stamp(path, deck_synced_at=_now_iso())


def deck_sync(acl: Acl, user_id: str, project: str, *, _deck, board_id, stack_id) -> dict:
    """Sync one Deck stack against the project's backlog. Owner only (it
    mutates both stores). Returns {created, updated_from_deck,
    updated_from_backlog, conflicts}."""
    acl.enforce(user_id, project, "owner")
    bl_dir = _backlog_dir(acl, project)

    cards = {str(c["id"]): c for c in _deck.list_cards(board_id, stack_id)}
    items = t_backlog.backlog_list(acl, user_id, project)
    linked = {str(i["deck_card_id"]): i for i in items if i.get("deck_card_id")}

    created: list[dict] = []
    updated_from_deck: list[str] = []
    updated_from_backlog: list[str] = []
    conflicts: list[dict] = []

    for card_id, card in cards.items():
        if card_id in linked:
            continue
        result = t_backlog.backlog_add(acl, user_id, project, card["title"], card["description"])
        path = bl_dir / f"{result['id']}.md"
        _stamp(path, deck_board_id=board_id, deck_stack_id=stack_id, deck_card_id=card_id, deck_synced_at=_now_iso())
        created.append({"backlog_id": result["id"], "deck_card_id": card_id})

    for card_id, item in linked.items():
        card = cards.get(card_id)
        if card is None:
            continue  # deleted on the Deck side — never delete the backlog item
        baseline = _parse_ts(item.get("deck_synced_at"))
        card_changed = card["last_modified"] > baseline
        item_changed = _parse_ts(item.get("updated_at")) > baseline
        path = bl_dir / f"{item['id']}.md"

        if card_changed and item_changed:
            if card["last_modified"] >= _parse_ts(item.get("updated_at")):
                _apply_deck_to_backlog(path, card)
                winner = "deck"
            else:
                _apply_backlog_to_deck(_deck, board_id, stack_id, card["id"], item, path)
                winner = "backlog"
            conflicts.append({"backlog_id": item["id"], "deck_card_id": card_id, "winner": winner})
        elif card_changed:
            _apply_deck_to_backlog(path, card)
            updated_from_deck.append(item["id"])
        elif item_changed:
            _apply_backlog_to_deck(_deck, board_id, stack_id, card["id"], item, path)
            updated_from_backlog.append(item["id"])

    return {
        "created": created,
        "updated_from_deck": updated_from_deck,
        "updated_from_backlog": updated_from_backlog,
        "conflicts": conflicts,
    }
