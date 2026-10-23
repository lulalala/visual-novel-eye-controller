"""GUI translations. The CLI never sets a language, so it stays English."""

from __future__ import annotations

import locale
import sys

from eyeokuri.locales import zh_tw

# Language code -> {"English text": "translated text"}. Imported statically so PyInstaller bundles them.
CATALOGS: dict[str, dict[str, str]] = {
    "zh-TW": zh_tw.CATALOG,
}

# Windows locale names (locale.windows_locale values) -> catalog code. Others get English.
_LOCALE_LANGUAGES = {
    "zh_TW": "zh-TW",
    "zh_HK": "zh-TW",
}

_active: dict[str, str] = {}


def _(text: str) -> str:
    """The translation of text in the active language, or text itself when there is none."""
    return _active.get(text, text)


def N_(text: str) -> str:
    """Marks a string in a module-level constant for translation; call _() where it is shown."""
    return text


def set_language(code: str) -> None:
    """Pick a catalog by code (a key of CATALOGS); any other code, such as "en", selects English."""
    global _active
    _active = CATALOGS.get(code, {})


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
