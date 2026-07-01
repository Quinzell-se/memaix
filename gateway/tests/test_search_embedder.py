# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for search.embedder."""

from __future__ import annotations

import math

from memaix_gateway.search.embedder import FakeEmbedder, make_embedder


def test_fake_embedder_deterministic():
    e = FakeEmbedder(dim=32)
    v1 = e.embed(["hello world"])[0]
    v2 = e.embed(["hello world"])[0]
    assert v1 == v2
    assert len(v1) == 32


def test_fake_embedder_similar_text_scores_higher_cosine():
    e = FakeEmbedder(dim=64)
    a, b, c = e.embed(["invoice payment overdue", "invoice payment late", "cat dog garden"])

    def cosine(x, y):
        dot = sum(xi * yi for xi, yi in zip(x, y))
        nx = math.sqrt(sum(xi * xi for xi in x)) or 1.0
        ny = math.sqrt(sum(yi * yi for yi in y)) or 1.0
        return dot / (nx * ny)

    assert cosine(a, b) > cosine(a, c)


def test_fake_embedder_empty_text():
    e = FakeEmbedder(dim=8)
    v = e.embed([""])[0]
    assert v == [0.0] * 8


def test_make_embedder_none_choice_returns_none():
    assert make_embedder({"embedder": "none"}) is None
    assert make_embedder({}) is None


def test_make_embedder_unknown_choice_returns_none():
    assert make_embedder({"embedder": "something-invalid"}) is None


def test_make_embedder_local_without_dependency_returns_none(monkeypatch):
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "sentence_transformers":
            raise ImportError("not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert make_embedder({"embedder": "local"}) is None
