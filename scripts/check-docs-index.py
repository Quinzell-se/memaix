#!/usr/bin/env python3
"""Doc-hygien: flagga om något docs/*.md saknas i INDEX.md.

SPDX-License-Identifier: AGPL-3.0-or-later

Kör lokalt eller i CI:  python3 scripts/check-docs-index.py
Exit 0 = alla dokument listade i INDEX. Exit 1 = något saknas.
"""

from __future__ import annotations

import sys
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "docs"
INDEX = DOCS / "INDEX.md"
SKIP = {"INDEX.md"}  # INDEX listar inte sig själv


def main() -> int:
    if not INDEX.exists():
        print("FEL: docs/INDEX.md saknas")
        return 1
    index_text = INDEX.read_text()
    docs = sorted(p.name for p in DOCS.glob("*.md") if p.name not in SKIP)
    missing = [d for d in docs if d not in index_text]

    if missing:
        print(f"FAIL: {len(missing)} dokument saknas i INDEX.md:")
        for d in missing:
            print(f"  - {d}")
        print("\nLägg in dem i rätt rollsektion och i snabbkartan.")
        return 1

    print(f"PASS: alla {len(docs)} dokument finns i INDEX.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
