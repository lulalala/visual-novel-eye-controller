"""GUI translations. The CLI never sets a language, so it stays English."""

from __future__ import annotations

import locale
import sys

from eyeokuri.locales import ja, zh_tw

# Language code -> {"English text": "translated text"}. Imported statically so PyInstaller bundles them.
CATALOGS: dict[str, dict[str, str]] = {
    "ja": ja.CATALOG,
    "zh-TW": zh_tw.CATALOG,
}

# Windows locale names (locale.windows_locale values) -> catalog code. Others get English.
_LOCALE_LANGUAGES = {
    "ja_JP": "ja",
    "zh_TW": "zh-TW",
    "zh_HK": "zh-TW",
}

# Language code -> (gap between sentences, full stop). Chinese and Japanese have no space after a sentence and end with 。.
_STYLES = {"ja": ("", "。"), "zh-TW": ("", "。")}

# Language code -> the language's name in itself, for the language picker. Not translated.
LANGUAGE_NAMES = {"en": "English", "ja": "日本語", "zh-TW": "繁體中文"}

_active: dict[str, str] = {}
_style = (" ", ".")


def _(text: str) -> str:
    """The translation of text in the active language, or text itself when there is none."""
    return _active.get(text, text)


def N_(text: str) -> str:
    """Marks a string in a module-level constant for translation; call _() where it is shown."""
    return text


def set_language(code: str) -> None:
    """Pick a catalog by code (a key of CATALOGS); any other code, such as "en", selects English."""
    global _active, _style
    _active = CATALOGS.get(code, {})
    _style = _STYLES.get(code, (" ", ".")) if code in CATALOGS else (" ", ".")


def gap() -> str:
    """What goes between two sentences: a space, or nothing in Chinese and Japanese."""
    return _style[0]


def stop() -> str:
    """The full stop that ends a sentence after a value, which the catalog can't hold."""
    return _style[1]


def language_for_locale(name: str) -> str:
    """The catalog code for a Windows locale name such as "zh_TW", or "en" when there is no catalog."""
    return _LOCALE_LANGUAGES.get(name, "en")


def resolve_language(setting: str) -> str:
    """The catalog code for the app.language setting: "auto" detects it, anything else is used as given."""
    return detect_language() if setting == "auto" else setting


def detect_language() -> str:
    """The catalog code matching the Windows display language, or "en" elsewhere or when unknown."""
    if sys.platform != "win32":
        return "en"
    import ctypes

    try:
        langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
    except (AttributeError, OSError):
        return "en"
    return language_for_locale(locale.windows_locale.get(langid, ""))
