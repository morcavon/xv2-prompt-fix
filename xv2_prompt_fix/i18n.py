from __future__ import annotations

import json
from pathlib import Path
from threading import RLock
from typing import Literal, cast

UiLanguage = Literal["ko", "en"]
_SUPPORTED_LANGUAGES: tuple[UiLanguage, ...] = ("ko", "en")
_LOCALE_PATH = Path(__file__).with_name("locales") / "ko.json"


def _load_korean_catalog() -> tuple[str, dict[str, str]]:
    data = json.loads(_LOCALE_PATH.read_text(encoding="utf-8"))
    language_name = data.get("language_name")
    translations = data.get("translations")
    if not isinstance(language_name, str) or not language_name:
        raise RuntimeError("The Korean locale language name is invalid.")
    if not isinstance(translations, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in translations.items()
    ):
        raise RuntimeError("The Korean locale translation table is invalid.")
    return language_name, cast(dict[str, str], translations)


_KOREAN_LANGUAGE_NAME, _KOREAN_TRANSLATIONS = _load_korean_catalog()
_lock = RLock()
_current_language: UiLanguage = "ko"


def available_languages() -> tuple[UiLanguage, ...]:
    return _SUPPORTED_LANGUAGES


def set_language(language: UiLanguage) -> None:
    if language not in _SUPPORTED_LANGUAGES:
        raise ValueError(f"Unsupported UI language: {language}")
    global _current_language
    with _lock:
        _current_language = language


def get_language() -> UiLanguage:
    with _lock:
        return _current_language


def language_name(language: UiLanguage) -> str:
    if language == "ko":
        return _KOREAN_LANGUAGE_NAME
    if language == "en":
        return "English"
    raise ValueError(f"Unsupported UI language: {language}")


def language_from_name(display_name: str) -> UiLanguage:
    for language in _SUPPORTED_LANGUAGES:
        if language_name(language) == display_name:
            return language
    raise ValueError(f"Unsupported UI language name: {display_name}")


def tr(text: str, /, **values: object) -> str:
    template = _KOREAN_TRANSLATIONS.get(text, text) if get_language() == "ko" else text
    return template.format(**values)
