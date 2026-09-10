# SPDX-License-Identifier: AGPL-3.0-or-later
"""Novelty gate — near-duplicate detection for memory_write.

check_novelty() compares incoming content against all existing memory chunks
in the project and returns the most similar note if it exceeds the threshold.
The caller decides whether to abort the write or proceed.

Gracefully returns None when no embedder is configured (lexical-only mode).
"""

from __future__ import annotations

import numpy as np


def check_novelty(
    content: str,
    project: str,
    current_note: str,
    embedder,
    store,
    threshold: float = 0.88,
) -> dict | None:
    """Return {"existing_path": str, "similarity": float} if *content* is a
    near-duplicate of an existing note in *project*, else None.

    Self-comparison is skipped so that overwriting an existing note (same path)
    is never blocked by its own previous content.
    """
    if embedder is None or not (content or "").strip():
        return None
    try:
        query_vec = embedder.embed([content])[0]
        candidates = store.candidates([project], ["memory"], 500)
        if not candidates:
            return None
        q = np.asarray(query_vec, dtype=np.float32)
        qn = float(np.linalg.norm(q)) or 1.0
        best_sim = 0.0
        best_ref = None
        for c in candidates:
            if c["ref"] == current_note:
                continue
            v = c["vector"]
            vn = float(np.linalg.norm(v)) or 1.0
            sim = float(np.dot(q, v) / (qn * vn))
            if sim > best_sim:
                best_sim = sim
                best_ref = c["ref"]
        if best_sim >= threshold and best_ref is not None:
            return {"existing_path": best_ref, "similarity": round(best_sim, 4)}
    except Exception:
        pass
    return None
