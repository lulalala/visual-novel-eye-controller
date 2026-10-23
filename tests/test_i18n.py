import ast
from pathlib import Path

import pytest

from eyeokuri import i18n
from eyeokuri.i18n import CATALOGS, N_, _, language_for_locale, set_language

SOURCE = Path(i18n.__file__).parent


@pytest.fixture(autouse=True)
def reset_language():
    yield
    set_language("en")


def test_untranslated_text_is_returned_unchanged():
    assert _("Nothing like this") == "Nothing like this"
    assert N_("Nothing like this") == "Nothing like this"


def test_translation_is_used_for_the_active_language(monkeypatch):
    monkeypatch.setitem(CATALOGS, "xx", {"Hello": "Salut"})
    set_language("xx")
    assert _("Hello") == "Salut"
    assert _("Missing") == "Missing"


def test_english_and_unknown_codes_use_the_source_text(monkeypatch):
    monkeypatch.setitem(CATALOGS, "xx", {"Hello": "Salut"})
    set_language("xx")
    set_language("en")
    assert _("Hello") == "Hello"
    set_language("nope")
    assert _("Hello") == "Hello"


@pytest.mark.parametrize("name, code", [
    ("zh_TW", "zh-TW"),
    ("zh_HK", "zh-TW"),
    ("zh_CN", "en"),
    ("ja_JP", "en"),
    ("", "en"),
    ("zz_ZZ", "en"),
])
def test_windows_locale_maps_to_a_catalog(name, code):
    assert language_for_locale(name) == code


def test_every_mapped_language_has_a_catalog():
    assert set(i18n._LOCALE_LANGUAGES.values()) <= set(CATALOGS)


def _marked_strings():
    """Literal arguments of _() and N_() calls in the source, and a problem for each non-literal N_()/f-string."""
    found: set[str] = set()
    problems: list[str] = []
    for path in sorted(SOURCE.rglob("*.py")):
        if path.parent.name == "locales" or path == Path(i18n.__file__):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("_", "N_")):
                continue
            arg = node.args[0] if node.args else None
            where = f"{path.name}:{node.lineno}"
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                found.add(arg.value)
            elif node.func.id == "N_" or isinstance(arg, ast.JoinedStr):
                problems.append(f"{where}: {node.func.id}() needs a plain string literal")
            # _(variable) shows a value marked with N_(); skip it.
    return found, problems


def test_marked_strings_are_plain_literals():
    _found, problems = _marked_strings()
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("code", sorted(CATALOGS))
def test_catalog_matches_the_source_strings(code):
    found, _problems = _marked_strings()
    catalog = CATALOGS[code]
    stale = sorted(set(catalog) - found)
    assert not stale, f"{code} has entries no longer in the source: {stale}"
    # A catalog still being filled in (empty) is allowed; once it has entries it must be complete.
    if catalog:
        missing = sorted(found - set(catalog))
        assert not missing, f"{code} is missing entries: {missing}"


def test_auto_language_detects_and_others_are_used_as_given(monkeypatch):
    monkeypatch.setattr(i18n, "detect_language", lambda: "zh-TW")
    assert i18n.resolve_language("auto") == "zh-TW"
    assert i18n.resolve_language("en") == "en"


def test_sentence_gap_and_stop_follow_the_language():
    assert (i18n.gap(), i18n.stop()) == (" ", ".")
    set_language("zh-TW")
    assert (i18n.gap(), i18n.stop()) == ("", "。")
    set_language("en")
    assert (i18n.gap(), i18n.stop()) == (" ", ".")
