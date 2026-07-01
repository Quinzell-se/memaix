# SPDX-License-Identifier: AGPL-3.0-or-later
"""Embedder abstraction — pluggable text-to-vector backend.

See docs/FEATURE-SEMANTIC-SEARCH.md §5. make_embedder(cfg) returns None when
no embedder is configured or the optional ML dependency isn't installed —
search_all() degrades to lexical (FTS5) search in that case, never crashes.
"""

from __future__ import annotations

import hashlib
import logging
import math
from typing import Protocol

logger = logging.getLogger(__name__)


class Embedder(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class FakeEmbedder:
    """Deterministic bag-of-words hash embedder — no ML dependency.

    Used in tests and as an always-available degradation path. Not a real
    semantic model: similar TEXT (shared tokens) scores higher, but it won't
    understand paraphrase/synonyms the way a real embedding model would.
    """

    def __init__(self, dim: int = 64) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        tokens = text.lower().split()
        if not tokens:
            return vec
        for tok in tokens:
            h = int(hashlib.sha256(tok.encode()).hexdigest(), 16)
            vec[h % self.dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


class LocalEmbedder:
    """Wraps a sentence-transformers model. Lazy-loaded on first use."""

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._model = None
        # Fail fast if the optional dependency truly isn't importable — the
        # caller (make_embedder) catches this and falls back to None.
        import sentence_transformers  # noqa: F401
        self.dim = 0  # resolved on first embed() call (model-dependent)

    def _ensure_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._model_name)
            self.dim = self._model.get_sentence_embedding_dimension()
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        model = self._ensure_model()
        return [list(map(float, v)) for v in model.encode(texts, normalize_embeddings=True)]


def make_embedder(cfg: dict) -> Embedder | None:
    """Build the configured embedder, or None (lexical-only fallback).

    cfg is the memaix.search config dict (e.g. {'embedder': 'local', 'model': '...'}).
    """
    choice = (cfg or {}).get("embedder", "none")
    if choice in (None, "none", ""):
        return None
    if choice == "local":
        model_name = cfg.get("model", "intfloat/multilingual-e5-small")
        try:
            return LocalEmbedder(model_name)
        except ImportError:
            logger.warning(
                "memaix.search.embedder=local but sentence-transformers isn't installed "
                "(pip install 'memaix-gateway[search]') — falling back to lexical-only search"
            )
            return None
    logger.warning("unknown memaix.search.embedder=%r — falling back to lexical-only search", choice)
    return None
