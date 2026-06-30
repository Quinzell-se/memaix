# SPDX-License-Identifier: AGPL-3.0-or-later
"""Minimal i18n: load JSON translation files, resolve keys with fallback to English."""

from __future__ import annotations

import json
from pathlib import Path

_LOCALES_DIR = Path(__file__).parent / "locales"
_SUPPORTED = {"en", "sv", "fr", "de", "es"}
_DEFAULT = "en"

_cache: dict[str, dict] = {}


def _load(locale: str) -> dict:
    if locale not in _cache:
        path = _LOCALES_DIR / f"{locale}.json"
        _cache[locale] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return _cache[locale]


def get_translator(locale: str):
    """Return a t(key) function for the given locale with English fallback."""
    loc = locale if locale in _SUPPORTED else _DEFAULT
    strings = _load(loc)
    fallback = _load(_DEFAULT) if loc != _DEFAULT else {}

    def t(key: str) -> str:
        return strings.get(key) or fallback.get(key) or key

    return t


def locale_from_request(accept_language: str | None, config_locale: str | None) -> str:
    """Pick locale: config > Accept-Language header > default (en)."""
    if config_locale and config_locale in _SUPPORTED:
        return config_locale
    if accept_language:
        for part in accept_language.split(","):
            lang = part.strip().split(";")[0].strip()[:2].lower()
            if lang in _SUPPORTED:
                return lang
    return _DEFAULT
