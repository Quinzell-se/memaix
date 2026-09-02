# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pydantic schema for backlog items (DEVELOPMENT-PROPOSALS.md §10).

frontmatter.py's split()/join() only guarantee "a dict came out of the YAML
block" — nothing checks that `status` is one of the real lifecycle values,
or that `value`/`complexity`/`risk` are the 1-5 scores MCP-API.md documents.
A hand-edited file or a slightly-off tool call could otherwise write
`status: 42` or `value: "high"` and have it propagate silently into every
reader (backlog_list, the board UI, reports).

BacklogItem is the single source of truth for that shape. tools/backlog.py
validates through it on every read (_parse_item) and write (_write_item);
pydantic's ValidationError subclasses ValueError, so it's caught by the
same `except (ValueError, yaml.YAMLError)` callers already use for
malformed frontmatter — no call-site changes needed beyond the two
functions that construct/serialise the dict.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

BacklogStatus = Literal["inbox", "triaged", "evaluated", "approved", "rejected", "in-dev", "done"]


class BacklogItem(BaseModel):
    model_config = ConfigDict(extra="allow")  # unknown frontmatter keys pass through untouched

    id: str
    title: str = Field(min_length=1)
    # Tomt som default: items skrivna innan fältet fanns saknar det, och en
    # obligatorisk author gjorde hela den befintliga backloggen oläsbar.
    # Skrivvägen sätter alltid ett riktigt värde.
    author: str = ""
    category: str | None = None
    status: BacklogStatus = "inbox"
    value: int | None = Field(default=None, ge=1, le=5)
    complexity: int | None = Field(default=None, ge=1, le=5)
    risk: int | None = Field(default=None, ge=1, le=5)
    assignee: str | None = None  # agent-/användarnamn (FEATURE-AGENT-TEAM fas 1); None = otilldelad
    version: int = Field(ge=1)
    created_at: str
    updated_at: str

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def _stamp_to_iso(cls, v: object) -> object:
        """YAML tolkar en ociterad ISO-tidsstämpel som datetime, inte str.

        Fälten lagras som text, men varje handredigerad fil — och allt som
        skrivits av ett äldre verktyg — ger ett datetime-objekt tillbaka.
        Att kräva str där gjorde giltiga poster ogiltiga."""
        if isinstance(v, (datetime, date)):
            return v.isoformat()
        return v
    description: str = ""
