from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

DEFAULT_LOCALE = "en"


def _locale_directory() -> Path:
    return Path(__file__).resolve().parent / "locales"


@lru_cache(maxsize=None)
def _load_catalog(locale: str) -> dict[str, str]:
    code = normalize_locale(locale)
    path = _locale_directory() / f"{code}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        if code != DEFAULT_LOCALE:
            return _load_catalog(DEFAULT_LOCALE)
        return {}
    return {str(key): str(value) for key, value in data.items()}


def available_locales() -> list[str]:
    directory = _locale_directory()
    try:
        codes = sorted(path.stem for path in directory.glob("*.json") if path.is_file())
    except OSError:
        codes = []
    if DEFAULT_LOCALE in codes:
        codes.remove(DEFAULT_LOCALE)
        codes.insert(0, DEFAULT_LOCALE)
    return codes or [DEFAULT_LOCALE]


def normalize_locale(locale: str | None) -> str:
    if not locale:
        return DEFAULT_LOCALE
    code = str(locale).strip().lower().replace("_", "-").split("-", 1)[0]
    return code if code in available_locales_uncached() else DEFAULT_LOCALE


def available_locales_uncached() -> set[str]:
    directory = _locale_directory()
    try:
        return {path.stem for path in directory.glob("*.json") if path.is_file()}
    except OSError:
        return {DEFAULT_LOCALE}


class Translator:
    def __init__(self, locale: str | None = None):
        self.locale = normalize_locale(locale)
        self.catalog = _load_catalog(self.locale)
        self.fallback = _load_catalog(DEFAULT_LOCALE)

    def t(self, key: str, **values: Any) -> str:
        template = self.catalog.get(key, self.fallback.get(key, key))
        try:
            return template.format(**values)
        except (KeyError, ValueError):
            return template

    def language_name(self, locale: str | None = None) -> str:
        code = normalize_locale(locale or self.locale)
        catalog = _load_catalog(code)
        return catalog.get("language.name", code)


def language_choices() -> list[tuple[str, str]]:
    return [(code, Translator(code).language_name()) for code in available_locales()]
