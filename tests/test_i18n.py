"""Messages, translation and the completeness of the catalogs."""
import ast
import copy
import json
import re
from pathlib import Path

import pytest

from dynamic_components import i18n
from dynamic_components.messages import MessageError, Msg, text_of

PKG = Path(__file__).resolve().parents[1] / "dynamic_components"
_FIELD = re.compile(r"{(\w+)}")


@pytest.fixture(autouse=True)
def english():
    i18n.set_language(None)
    yield
    i18n.set_language(None)


def test_msg_is_its_english_text():
    m = Msg("Unknown part {part}", part="'x'")
    assert m == "Unknown part 'x'" and isinstance(m, str) and "part" in m
    assert m.template == "Unknown part {part}" and m.params == {"part": "'x'"}
    assert Msg("Literal {braces}") == "Literal {braces}"


def test_msg_survives_copies_and_json():
    m = Msg("Copy {index}: {error}", index=2, error=Msg("Division by zero"))
    for twin in (copy.deepcopy(m), Msg.from_json(json.loads(json.dumps(m.to_json())))):
        assert twin == m and twin.template == m.template
        assert isinstance(twin.params["error"], Msg)


@pytest.mark.parametrize("data", [None, "x", {"t": 1}, {"t": "a", "p": []},
                                  {"t": "a", "p": {"bad key": 1}},
                                  {"t": "a", "p": {"k": object()}}, {"t": "x" * 5000}])
def test_stored_messages_from_strangers_are_checked(data):
    assert Msg.from_json(data) is None


def test_message_errors_keep_their_msg():
    exc = MessageError(Msg("Hole {n}", n=3))
    assert str(exc) == "Hole 3" and text_of(exc).template == "Hole {n}"
    plain = MessageError("plain {text}")
    assert str(plain) == "plain {text}" and text_of(ValueError("v")) == "v"


def test_german_translation_of_messages_and_their_words():
    i18n.set_language("de")
    nested = Msg("Copy {index}: {error}", index=2, error=Msg("Division by zero"))
    assert i18n.tr_msg(nested) == "Kopie 2: Division durch null"
    assert i18n.tr_msg(Msg("{what} must be a number", what="Value")) == "Wert muss eine Zahl sein"
    assert i18n.tr("Bake") == "Einfrieren"
    assert i18n.tr("No such string anywhere") == "No such string anywhere"
    assert i18n.tr_error(ValueError(Msg("Nothing to add."))) == "Nichts hinzuzufügen."


def test_unknown_language_falls_back_to_english():
    i18n.set_language("xx")
    assert i18n.tr("Bake") == "Bake"
    assert i18n.tr_msg(Msg("Division by zero")) == "Division by zero"


def _strings():
    """Every source string the code translates: tr/N_/Msg literals."""
    found = {}
    for path in PKG.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name not in ("tr", "N_", "Msg"):
                continue
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                found.setdefault(arg.value, f"{path.name}:{node.lineno}")
            elif isinstance(arg, ast.JoinedStr):
                raise AssertionError(f"{path.name}:{node.lineno}: f-string passed to {name}")
    return found


def test_catalogs_are_complete_and_keep_placeholders():
    strings = _strings()
    assert len(strings) > 150
    langs = [lang for lang in i18n.available() if lang != "en"]
    assert {"de", "es", "fr"} <= set(langs)
    for lang in langs:
        table = json.loads((PKG / "locale" / f"{lang}.json").read_text(encoding="utf-8"))
        missing = sorted(s for s in strings if s not in table)
        assert not missing, f"{lang}: missing {missing[:10]}"
        stale = sorted(s for s in table if s not in strings)
        assert not stale, f"{lang}: unused {stale[:10]}"
        for source, text in table.items():
            assert set(_FIELD.findall(source)) == set(_FIELD.findall(text)), (lang, source)


def test_french():
    i18n.set_language("fr")
    assert i18n.tr("Bake") == "Figer"
    assert i18n.tr_msg(Msg("Copy {index}: {error}", index=1,
                           error=Msg("Division by zero"))) == "Copie 1 : Division par zéro"
    i18n.set_language("fr-CA")                              # regional: base language
    assert i18n.tr("Make dynamic") == "Rendre dynamique"


def test_english_is_the_source_and_the_fallback(monkeypatch):
    table = json.loads((PKG / "locale" / "en.json").read_text(encoding="utf-8"))
    assert set(table) == {"_comment"}                        # identity map, kept empty
    i18n.set_language("en")
    assert i18n.tr("Bake") == "Bake" and i18n.tr("_comment") == "_comment"
    for lang in ("pt-BR", "xx", ""):
        i18n.set_language(lang)
        assert i18n.tr("Make dynamic") == "Make dynamic"
    # a string missing from a catalog shows in English
    i18n.set_language("de")
    monkeypatch.setitem(i18n._catalogs, "de", {"Bake": "Einfrieren"})
    assert i18n.tr("Bake") == "Einfrieren" and i18n.tr("Make dynamic") == "Make dynamic"
    assert i18n.tr_msg(Msg("Unknown part {part}", part="'x'")) == "Unknown part 'x'"


def test_shipped_languages():
    assert {"en", "de", "es", "fr"} <= set(i18n.available())
