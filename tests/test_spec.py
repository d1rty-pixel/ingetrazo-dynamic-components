import copy
import json

import pytest

from dynamic_components import spec
from dynamic_components.spec import SpecError, coerce, editable_attrs, normalize


def a(**kw):
    kw.setdefault("type", "length")
    return kw


def minimal():
    return {"version": 1, "name": "Door", "nodes": {
        "": {"attrs": {"Width": a(value=0.9, access="textbox", label="Width")},
             "rest": {"size": [1, 2, 3]}},
        "Leaf": {"label": "Leaf", "attrs": {"LenX": a(formula="=Width-0.1"), "X": a(value=1)},
                 "rest": {"xform": list(range(16)), "size": [1, 1, 1]}}}}


def test_normalize_lowercases_and_fills_defaults():
    out = normalize(minimal())
    assert list(out["nodes"]) == ["", "leaf"]
    assert list(out["nodes"][""]["attrs"]) == ["width"]
    width = out["nodes"][""]["attrs"]["width"]
    assert width == {"label": "Width", "type": "length", "value": 0.9, "formula": None,
                     "access": "textbox"}
    lenx = out["nodes"]["leaf"]["attrs"]["lenx"]
    assert lenx["access"] == "none" and lenx["label"] == "LenX" and lenx["value"] == 0.0
    assert lenx["formula"] == "=Width-0.1"
    assert out["nodes"]["leaf"]["rest"]["xform"] == [float(i) for i in range(16)]
    assert json.loads(json.dumps(out)) == out


def test_normalize_is_deep_copy_and_idempotent():
    src = minimal()
    before = copy.deepcopy(src)
    out = normalize(src)
    assert src == before
    assert normalize(out) == out
    out["nodes"][""]["attrs"]["width"]["value"] = 5
    assert src == before


def test_normalize_adds_root_and_labels():
    out = normalize({"name": "N", "nodes": {"Part": {}}})
    assert list(out["nodes"]) == ["", "part"]
    assert out["nodes"]["part"]["label"] == "Part"
    assert out["nodes"][""]["label"] == "N"
    assert normalize({})["nodes"][""]["attrs"] == {}


def test_root_len_value_stays_open():
    out = normalize({"nodes": {"": {"attrs": {"lenx": {}}}}})
    attr = out["nodes"][""]["attrs"]["lenx"]
    assert attr["type"] == "length" and attr["value"] is None
    assert normalize(out) == out


def test_reserved_types():
    out = normalize({"nodes": {"p": {"attrs": {
        "hidden": {}, "copies": {}, "rotx": {}, "material": {}, "x": {}}}}})
    types = {k: v["type"] for k, v in out["nodes"]["p"]["attrs"].items()}
    assert types == {"hidden": "bool", "copies": "int", "rotx": "float",
                     "material": "material", "x": "length"}
    with pytest.raises(SpecError):
        normalize({"nodes": {"p": {"attrs": {"hidden": {"type": "string"}}}}})
    with pytest.raises(SpecError, match="read-only"):
        normalize({"nodes": {"p": {"attrs": {"copy": {}}}}})
    assert {"copy", "copies", "lenx", "hidden"} <= spec.RESERVED
    assert len(spec.RESERVED) == 13


def test_invalid_formula_is_kept():
    out = normalize({"nodes": {"": {"attrs": {"w": a(formula="=1+")}}}})
    assert out["nodes"][""]["attrs"]["w"]["formula"] == "=1+"


@pytest.mark.parametrize("bad", [
    None, [], "x", {"version": 2}, {"version": True}, {"name": 5}, {"nodes": []},
    {"nodes": {"a": 5}}, {"nodes": {"a": {"attrs": []}}},
    {"nodes": {"a b": {}}}, {"nodes": {"1a": {}}}, {"nodes": {"self": {}}},
    {"nodes": {"Parent": {}}}, {"nodes": {"A": {}, "a": {}}},
    {"nodes": {"": {"attrs": {"": {}}}}}, {"nodes": {"": {"attrs": {"a b": {}}}}},
    {"nodes": {"": {"attrs": {"A": {}, "a": {}}}}},
    {"nodes": {"": {"attrs": {"a": 5}}}},
    {"nodes": {"": {"attrs": {"a": {"type": "nope"}}}}},
    {"nodes": {"": {"attrs": {"a": {"access": "nope"}}}}},
    {"nodes": {"": {"attrs": {"a": {"formula": 5}}}}},
    {"nodes": {"": {"attrs": {"a": {"label": 5}}}}},
    {"nodes": {"": {"attrs": {"a": {"min": "x"}}}}},
    {"nodes": {"": {"attrs": {"a": {"min": float("nan")}}}}},
    {"nodes": {"": {"attrs": {"a": {"min": 5, "max": 1}}}}},
    {"nodes": {"": {"attrs": {"a": {"type": "length", "value": "abc"}}}}},
    {"nodes": {"": {"attrs": {"a": {"value": float("inf")}}}}},
    {"nodes": {"": {"attrs": {"a": {"value": 10 ** 400}}}}},
    {"nodes": {"": {"attrs": {"a": {"value": {"x": 1}}}}}},
    {"nodes": {"": {"attrs": {"a": {"options": 5}}}}},
    {"nodes": {"": {"attrs": {"a": {"options": [["x"]]}}}}},
    {"nodes": {"": {"attrs": {"a": {"options": [[1, 1]]}}}}},
    {"nodes": {"": {"attrs": {"a": {"options": [["x", [1]]]}}}}},
    {"nodes": {"": {"attrs": {"a": {"type": "choice", "options": [["a", "A"]], "value": "Z"}}}}},
    {"nodes": {"": {"rest": []}}}, {"nodes": {"": {"rest": {"xform": [1] * 15}}}},
    {"nodes": {"": {"rest": {"xform": [1] * 15 + [float("inf")]}}}},
    {"nodes": {"": {"rest": {"xform": "x" * 16}}}},
    {"nodes": {"": {"rest": {"size": [1, 2]}}}}, {"nodes": {"": {"rest": {"size": [1, -1, 1]}}}},
    {"nodes": {"": {"rest": {"size": [1, 2, float("nan")]}}}},
    {"nodes": {"": {"rest": {"size": [True, 1, 1]}}}},
])
def test_normalize_rejects(bad):
    with pytest.raises(SpecError):
        normalize(bad)


def test_limits():
    nodes = {f"n{i}": {} for i in range(256)}
    with pytest.raises(SpecError, match="nodes"):
        normalize({"nodes": nodes})
    nodes = {f"n{i}": {} for i in range(255)}
    assert len(normalize({"nodes": nodes})["nodes"]) == 256
    attrs = {f"a{i}": {} for i in range(257)}
    with pytest.raises(SpecError, match="attributes"):
        normalize({"nodes": {"": {"attrs": attrs}}})
    assert normalize({"nodes": {"": {"attrs": {f"a{i}": {} for i in range(256)}}}})
    with pytest.raises(SpecError):
        normalize({"nodes": {"": {"attrs": {"a": {"label": "x" * 5000}}}}})
    with pytest.raises(SpecError):
        normalize({"nodes": {"": {"attrs": {"a": {"formula": "x" * 70000}}}}})
    with pytest.raises(SpecError):
        normalize({"nodes": {"": {"attrs": {"a": {"type": "string", "value": "x" * 70000}}}}})


def test_value_defaults_per_type():
    out = normalize({"nodes": {"": {"attrs": {
        "l": a(), "i": a(type="int"), "b": a(type="bool"), "s": a(type="string"),
        "m": a(type="material"),
        "c": a(type="choice", options=[["One", "1"], ["Two", "2"]], access="list")}}}})
    values = {k: v["value"] for k, v in out["nodes"][""]["attrs"].items()}
    assert values == {"l": 0.0, "i": 0, "b": False, "s": "", "m": "", "c": "1"}
    assert out["nodes"][""]["attrs"]["c"]["options"] == [["One", "1"], ["Two", "2"]]


def test_value_is_coerced_and_clamped_on_normalize():
    out = normalize({"nodes": {"": {"attrs": {"w": a(value=5, min=1, max=2)}}}})
    assert out["nodes"][""]["attrs"]["w"]["value"] == 2.0
    assert isinstance(out["nodes"][""]["attrs"]["w"]["value"], float)


def test_editable_attrs_order():
    out = normalize({"nodes": {
        "p": {"attrs": {"a": a(access="textbox"), "b": a(access="view")}},
        "": {"attrs": {"z": a(access="list"), "y": a(access="none")}},
        "q": {"attrs": {"c": a(access="list")}}}})
    got = [(n, k) for n, k, _ in editable_attrs(out)]
    assert got == [("", "z"), ("p", "a"), ("q", "c")]
    assert editable_attrs({"nodes": {}}) == []


# ------------------------------------------------------------------- coerce

@pytest.mark.parametrize("kind", ["length", "float"])
def test_coerce_float(kind):
    attr = {"type": kind}
    assert coerce(attr, 1) == 1.0 and type(coerce(attr, 1)) is float
    assert coerce(attr, "2.5") == 2.5
    assert coerce(attr, " 3 ") == 3.0
    assert coerce(attr, True) == 1.0
    for bad in ("abc", "", "nan", "inf", "1_0", None, [1], float("nan"),
                float("inf"), 10 ** 400, "1e999"):
        with pytest.raises(SpecError):
            coerce(attr, bad)


def test_coerce_clamp():
    attr = {"type": "length", "min": 1.0, "max": 2.0}
    assert coerce(attr, 0) == 1.0 and coerce(attr, 9) == 2.0 and coerce(attr, 1.5) == 1.5
    assert coerce({"type": "int", "min": 1, "max": 3}, 7) == 3
    assert coerce({"type": "float", "min": 0}, -1) == 0.0
    assert coerce({"type": "float", "max": 0}, 1) == 0.0


def test_coerce_int():
    attr = {"type": "int"}
    assert coerce(attr, 2.5) == 3 and coerce(attr, 2.4) == 2 and coerce(attr, "7") == 7
    assert coerce(attr, -2.5) == -2 and type(coerce(attr, 2.0)) is int
    assert coerce(attr, True) == 1
    with pytest.raises(SpecError):
        coerce(attr, 1e30)
    with pytest.raises(SpecError):
        coerce(attr, "x")


def test_coerce_bool():
    attr = {"type": "bool"}
    assert coerce(attr, True) is True and coerce(attr, 0) is False and coerce(attr, 2.5) is True
    assert coerce(attr, "True") is True and coerce(attr, "no") is False
    for bad in ("maybe", None, [1], float("nan")):
        with pytest.raises(SpecError):
            coerce(attr, bad)


def test_coerce_string_and_material():
    for kind in ("string", "material"):
        attr = {"type": kind}
        assert coerce(attr, "x") == "x" and coerce(attr, 5) == "5" and coerce(attr, 1.5) == "1.5"
        assert coerce(attr, None) == "" and coerce(attr, True) == "TRUE"
        with pytest.raises(SpecError):
            coerce(attr, ["a"])
        with pytest.raises(SpecError):
            coerce(attr, "x" * 70000)


def test_coerce_choice():
    attr = {"type": "choice", "options": [["Narrow", 0.8], ["Wide", 1.0], ["Name", "n"]]}
    assert coerce(attr, 0.8) == 0.8 and coerce(attr, 1) == 1.0 and coerce(attr, "n") == "n"
    assert coerce(attr, "0.8") == 0.8
    with pytest.raises(SpecError):
        coerce(attr, 0.9)
    with pytest.raises(SpecError):
        coerce({"type": "choice", "options": [["T", True]]}, 1)
    assert coerce({"type": "choice"}, "anything") == "anything"
    with pytest.raises(SpecError):
        coerce({"type": "choice"}, {"a": 1})


def test_coerce_unknown_type():
    with pytest.raises(SpecError):
        coerce({"type": "weird"}, 1)


def test_section_show_if_and_warn_are_kept():
    s = minimal()
    s["nodes"][""]["attrs"]["Width"].update(section="Carcass", show_if="=TRUE")
    s["nodes"][""]["attrs"]["Note"] = {"type": "string", "access": "warn", "formula": '="x"'}
    out = normalize(s)["nodes"][""]["attrs"]
    assert out["width"]["section"] == "Carcass" and out["width"]["show_if"] == "=TRUE"
    assert out["note"]["access"] == "warn"
    assert "section" not in out["note"] and "show_if" not in out["note"]
    s["nodes"][""]["attrs"]["Width"]["section"] = "x" * 300
    with pytest.raises(SpecError):
        normalize(s)


def test_generator_and_cutter_links():
    s = minimal()
    s["nodes"]["Side"] = {"gen": "Board@1", "attrs": {}}
    s["nodes"]["Hole"] = {"cut": "Side", "attrs": {}}
    out = normalize(s)["nodes"]
    assert out["side"]["gen"] == "board@1" and out["hole"]["cut"] == "side"
    assert "gen" not in out["leaf"] and "cut" not in out["leaf"]


@pytest.mark.parametrize("nodes", [
    {"Side": {"gen": "board"}},                              # no version
    {"Side": {"gen": "board@1; rm"}},
    {"Hole": {"cut": "Nowhere"}},
    {"Hole": {"cut": "Hole"}},                               # itself
    {"Hole": {"cut": ""}, "Hole2": {"cut": "Hole3"}},
    {"Hole": {"cut": "Leaf", "gen": "board@1"}},             # both
    {"A": {"cut": "Leaf"}, "B": {"cut": "A"}},               # cuts a cutter
])
def test_bad_links_are_refused(nodes):
    s = minimal()
    for name, body in nodes.items():
        s["nodes"][name] = {"attrs": {}, **body}
    with pytest.raises(SpecError):
        normalize(s)


def test_root_cannot_be_generated_or_cut():
    s = minimal()
    s["nodes"][""]["gen"] = "board@1"
    with pytest.raises(SpecError):
        normalize(s)
    s = minimal()
    s["nodes"][""]["cut"] = "leaf"
    with pytest.raises(SpecError):
        normalize(s)


def test_spec_errors_are_translatable():
    with pytest.raises(SpecError) as exc:
        normalize({"version": 2})
    assert exc.value.msg.template == "Unsupported spec version {version}"
