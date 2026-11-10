import time

import pytest

from dynamic_components import evaluate as ev_mod
from dynamic_components.evaluate import Placement, Result, evaluate
from dynamic_components.spec import SpecError


def L(**kw):
    kw.setdefault("type", "length")
    return kw


def build(root=None, **parts):
    nodes = {"": {"attrs": root or {}}}
    for name, attrs in parts.items():
        nodes[name] = {"attrs": attrs}
    return {"version": 1, "nodes": nodes}


def test_dataclasses_shape():
    p = Placement(copy=0)
    assert p.x is None and p.hidden is None and p.material is None
    assert Result({}, {}, {}).errors == {}


def test_plain_values_and_part_placements():
    spec = build({"w": L(value=2)}, leaf={"lenx": L(value=1.5), "hidden": {"type": "bool", "value": True}})
    r = evaluate(spec, {})
    assert r.values == {"": {"w": 2.0}, "leaf": {"lenx": 1.5, "hidden": True}}
    pl = r.placements["leaf"]
    assert len(pl) == 1 and pl[0].lenx == 1.5 and pl[0].hidden is True
    assert pl[0].x is None and pl[0].material is None and pl[0].copy == 0
    assert "" not in r.placements and r.errors == {}


def test_formula_chain_across_nodes_any_order():
    spec = build({"a": L(formula="=b*2"), "b": L(formula="=Leaf!lenx+1")},
                 leaf={"lenx": L(formula="=1+1")})
    r = evaluate(spec, {})
    assert r.values[""] == {"a": 6.0, "b": 3.0} and r.errors == {}
    assert r.placements["leaf"][0].lenx == 2.0


def test_parent_and_sibling_refs_case_insensitive():
    spec = build({"Width": L(value=4)}, Left={"X": L(value=1)},
                 Right={"X": L(formula="=PARENT!width - left!x"), "LenX": L(formula="=Self!x")})
    r = evaluate(spec, {})
    assert r.values["right"] == {"x": 3.0, "lenx": 3.0}
    assert r.placements["right"][0].x == 3.0


def test_override_beats_value_but_not_formula():
    spec = build({"w": L(value=1), "f": L(value=1, formula="=w*10")})
    r = evaluate(spec, {"": {"w": 3, "f": 99}})
    assert r.values[""] == {"w": 3.0, "f": 30.0}
    assert r.errors == {}


def test_override_keys_case_insensitive_and_unknown_ignored():
    spec = build({"w": L(value=1)})
    r = evaluate(spec, {"": {"W": 5, "nope": 1}, "ghost": {"a": 1}, "x": 5})
    assert r.values[""]["w"] == 5.0
    assert evaluate(spec, None).values[""]["w"] == 1.0


def test_root_overrides_beat_formulas():
    spec = build({"lenx": L(formula="=1+1"), "x": L(formula="=5"), "z": L(formula="=1"),
                  "other": L(formula="=2")})
    r = evaluate(spec, {"": {"lenx": 9, "x": 3, "other": 7}})
    assert r.values[""]["lenx"] == 9.0 and r.values[""]["x"] == 3.0
    assert r.values[""]["z"] == 1.0 and r.values[""]["other"] == 2.0


def test_root_override_formula_wins_even_if_formula_broken_or_cyclic():
    spec = build({"lenx": L(formula="=1+"), "leny": L(formula="=leny+1")})
    r = evaluate(spec, {"": {"lenx": 2, "leny": 3}})
    assert r.values[""] == {"lenx": 2.0, "leny": 3.0} and r.errors == {}


def test_part_len_override_does_not_beat_formula():
    spec = build(p={"lenx": L(formula="=4")})
    assert evaluate(spec, {"p": {"lenx": 9}}).values["p"]["lenx"] == 4.0


def test_root_len_defaults_to_rest_size():
    spec = {"nodes": {"": {"rest": {"size": [1, 2, 3]}},
                      "p": {"attrs": {"lenx": L(formula="=Parent!LenX*2 + Parent!lenz")}}}}
    r = evaluate(spec, {})
    assert r.values[""] == {"lenx": 1.0, "leny": 2.0, "lenz": 3.0}
    assert r.values["p"]["lenx"] == 5.0
    r = evaluate(spec, {"": {"lenx": 10}})
    assert r.values[""]["lenx"] == 10.0 and r.values["p"]["lenx"] == 23.0


def test_declared_root_len_without_value_uses_rest_size_and_explicit_value_wins():
    spec = {"nodes": {"": {"attrs": {"lenx": {}, "leny": {"value": 7}}, "rest": {"size": [1, 2, 3]}}}}
    r = evaluate(spec, {})
    assert r.values[""]["lenx"] == 1.0 and r.values[""]["leny"] == 7.0


def test_no_rest_size_no_synthetic_attrs():
    assert evaluate(build({"a": L(value=1)}), {}).values[""] == {"a": 1.0}


def test_types_coerced():
    spec = build({"n": {"type": "int", "formula": "=2.5"}, "s": {"type": "string", "formula": "=1+1"},
                  "b": {"type": "bool", "formula": "=1>0"}, "w": L(formula="=TRUE")})
    r = evaluate(spec, {})
    assert r.values[""] == {"n": 3, "s": "2", "b": True, "w": 1.0}
    assert type(r.values[""]["n"]) is int


def test_string_result_for_numeric_attr_is_error_and_falls_back():
    spec = build({"w": L(value=2, formula='="abc"'), "n": L(value=3, formula='="5"'),
                  "b": {"type": "bool", "formula": '="TRUE"'}})
    r = evaluate(spec, {})
    assert r.values[""]["w"] == 2.0 and r.values[""]["n"] == 3.0 and r.values[""]["b"] is False
    assert set(r.errors) == {("", "w"), ("", "n"), ("", "b")}


def test_clamp_and_choice_results():
    spec = build({"w": L(formula="=100", max=2), "c": {"type": "choice", "options": [["A", "a"], ["B", "b"]],
                                                       "formula": '="b"'},
                  "bad": {"type": "choice", "options": [["A", "a"]], "value": "a", "formula": '="z"'}})
    r = evaluate(spec, {})
    assert r.values[""] == {"w": 2.0, "c": "b", "bad": "a"} and list(r.errors) == [("", "bad")]


def test_fail_closed_to_last_then_value():
    spec = build({"a": L(value=1, formula="=1/0"), "b": L(value=2, formula="=1/0"),
                  "c": L(formula="=a+b")})
    r = evaluate(spec, {}, {"": {"a": 7}})
    assert r.values[""] == {"a": 7.0, "b": 2.0, "c": 9.0}
    assert set(r.errors) == {("", "a"), ("", "b")}
    assert "zero" in r.errors[("", "a")]


def test_last_invalid_falls_to_value_and_override_ignored_on_failure():
    spec = build({"a": L(value=1, formula="=1/0")})
    r = evaluate(spec, {"": {"a": 50}}, {"": {"a": "junk"}})
    assert r.values[""]["a"] == 1.0
    r = evaluate(spec, {}, {"": {"a": None}})
    assert r.values[""]["a"] == 1.0


def test_syntax_error_is_local():
    spec = build({"bad": L(value=4, formula="=1+"), "ok": L(formula="=bad+1")})
    r = evaluate(spec, {})
    assert r.values[""] == {"bad": 4.0, "ok": 5.0} and list(r.errors) == [("", "bad")]


def test_unknown_refs_are_local_errors():
    spec = build({"a": L(value=1, formula="=ghost!x"), "b": L(value=2, formula="=nothing"),
                  "c": L(value=3, formula="=leaf!nothing"), "ok": L(formula="=1")},
                 leaf={"x": L(value=1)})
    r = evaluate(spec, {})
    assert r.values[""] == {"a": 1.0, "b": 2.0, "c": 3.0, "ok": 1.0}
    assert set(r.errors) == {("", "a"), ("", "b"), ("", "c")}
    assert "ghost" in r.errors[("", "a")]


def test_unknown_ref_in_untaken_branch_is_fine():
    spec = build({"a": L(formula="=IF(1, 5, ghost!x)")})
    r = evaluate(spec, {})
    assert r.values[""]["a"] == 5.0 and r.errors == {}


def test_root_parent_ref_is_error():
    r = evaluate(build({"a": L(value=1, formula="=Parent!x")}), {})
    assert ("", "a") in r.errors


def test_cycle_detection_reports_every_member():
    spec = build({"a": L(value=1, formula="=b+1"), "b": L(value=2, formula="=c+1"),
                  "c": L(value=3, formula="=a+1"), "d": L(formula="=a+b+c")})
    r = evaluate(spec, {}, {"": {"b": 10}})
    assert {k for k in r.errors} == {("", "a"), ("", "b"), ("", "c")}
    assert r.values[""] == {"a": 1.0, "b": 10.0, "c": 3.0, "d": 14.0}
    assert "ircular" in r.errors[("", "a")]


def test_self_reference_and_cross_node_cycle():
    spec = build({"a": L(value=1, formula="=a+1"), "t": L(value=1, formula="=leaf!x")},
                 leaf={"x": L(value=2, formula="=parent!t")})
    r = evaluate(spec, {})
    assert set(r.errors) == {("", "a"), ("", "t"), ("leaf", "x")}
    assert r.values[""]["a"] == 1.0 and r.values["leaf"]["x"] == 2.0


def test_cycle_does_not_poison_independent_attrs():
    spec = build({"a": L(formula="=b"), "b": L(formula="=a"), "ok": L(formula="=2*3")})
    r = evaluate(spec, {})
    assert r.values[""]["ok"] == 6.0 and ("", "ok") not in r.errors


def test_long_dependency_chain_no_recursion_problem():
    n = 250
    attrs = {"a0": L(value=1)}
    for i in range(1, n):
        attrs[f"a{i}"] = L(formula=f"=a{i - 1}+1")
    r = evaluate(build(attrs), {})
    assert r.values[""][f"a{n - 1}"] == float(n) and r.errors == {}


def test_budget_exhaustion_falls_back():
    deep = "=" + "IF(1," * 40 + "1" + ",0)" * 40
    bomb = "=" + "CHOOSE(1," * 30 + "1" + ",0)" * 30
    assert len(deep) < 4096
    spec = build({"a": L(value=5, formula="=" + "1+" * 3000 + "1"), "b": L(value=6, formula=bomb)})
    r = evaluate(spec, {})
    assert r.values[""]["a"] == 5.0 and ("", "a") in r.errors
    assert r.values[""]["b"] == 1.0


def test_total_budget_exhaustion(monkeypatch):
    monkeypatch.setattr(ev_mod, "TOTAL_BUDGET", 30)
    attrs = {f"a{i}": L(value=-1, formula="=1+1+1+1") for i in range(20)}
    r = evaluate(build(attrs), {})
    values = list(r.values[""].values())
    assert 4.0 in values and -1.0 in values and r.errors


def test_hostile_formulas_never_raise():
    nasty = ["=__import__('os')", "=1e999", "=" + "9" * 500, "=" + "(" * 500 + "1" + ")" * 500,
             "=" + "x" * 5000, "=1/0", "=SQRT(-1)", '="a"+1', "=10^400", "", "=)"]
    spec = build({f"a{i}": L(value=i, formula=f) for i, f in enumerate(nasty)})
    r = evaluate(spec, {})
    assert r.values[""]["a0"] == 0.0 and r.values[""]["a2"] == 2.0
    assert r.values[""]["a9"] == 9.0  # empty formula means "no formula"


def test_bad_spec_raises_specerror():
    with pytest.raises(SpecError):
        evaluate({"version": 9}, {})


def test_invalid_override_value_ignored_with_error():
    spec = build({"w": L(value=1)})
    r = evaluate(spec, {"": {"w": "abc"}})
    assert r.values[""]["w"] == 1.0 and ("", "w") in r.errors


def test_override_clamped():
    spec = build({"w": L(value=1, max=2)})
    assert evaluate(spec, {"": {"w": 5}}).values[""]["w"] == 2.0


# ------------------------------------------------------------------- copies

def fence(copies="=3", x="=COPY*2"):
    return build({"w": L(value=10)}, post={
        "copies": {"type": "int", "formula": copies}, "x": L(formula=x),
        "lenx": L(formula="=Parent!w/10"), "hidden": {"type": "bool", "formula": "=COPY=2"}})


def test_copies_basic():
    r = evaluate(fence(), {})
    pl = r.placements["post"]
    assert [p.copy for p in pl] == [0, 1, 2, 3]
    assert [p.x for p in pl] == [0.0, 2.0, 4.0, 6.0]
    assert all(p.lenx == 1.0 for p in pl)
    assert [p.hidden for p in pl] == [False, False, True, False]
    assert r.values["post"]["x"] == 0.0 and r.values["post"]["copies"] == 3 and r.errors == {}


def test_copy_zero_outside_copies_and_readonly():
    spec = build({"c": L(formula="=Copy"), "d": L(formula="=Post!copy")}, post={
        "copies": {"type": "int", "value": 2}, "x": L(formula="=copy")})
    r = evaluate(spec, {})
    assert r.values[""] == {"c": 0.0, "d": 0.0} and r.values["post"]["x"] == 0.0
    assert [p.x for p in r.placements["post"]] == [0.0, 1.0, 2.0]


def test_copy_cannot_be_overridden():
    spec = build(p={"copies": {"type": "int", "value": 1}, "x": L(formula="=copy")})
    r = evaluate(spec, {"p": {"copy": 5}})
    assert [p.x for p in r.placements["p"]] == [0.0, 1.0]


def test_copies_transitive_dependents_and_independent_attrs():
    spec = build(post={"copies": {"type": "int", "value": 2}, "a": L(formula="=copy*10"),
                       "x": L(formula="=a+1"), "y": L(formula="=5")})
    pl = evaluate(spec, {}).placements["post"]
    assert [p.x for p in pl] == [1.0, 11.0, 21.0] and [p.y for p in pl] == [5.0] * 3


def test_other_nodes_use_copy_zero_values():
    spec = build({"t": L(formula="=Post!x")}, post={
        "copies": {"type": "int", "value": 2}, "x": L(formula="=copy*5")})
    r = evaluate(spec, {})
    assert r.values[""]["t"] == 0.0


def test_part_references_itself_by_name_in_copy():
    spec = build(post={"copies": {"type": "int", "value": 2}, "a": L(formula="=Post!copy"),
                       "x": L(formula="=Post!a+1")})
    assert [p.x for p in evaluate(spec, {}).placements["post"]] == [1.0, 2.0, 3.0]


def test_copies_clamped_and_reported():
    spec = build(p={"copies": {"type": "int", "formula": "=5000"}})
    r = evaluate(spec, {}, max_copies=10)
    assert len(r.placements["p"]) == 11 and ("p", "copies") in r.errors
    assert "10" in r.errors[("p", "copies")]
    assert len(evaluate(spec, {}).placements["p"]) == 1001


def test_negative_copies_clamped_to_zero():
    spec = build(p={"copies": {"type": "int", "formula": "=-4"}})
    r = evaluate(spec, {})
    assert len(r.placements["p"]) == 1 and ("p", "copies") in r.errors


def test_copies_zero_and_missing_attr():
    spec = build(p={"copies": {"type": "int", "value": 0}}, q={"x": L(value=1)})
    r = evaluate(spec, {})
    assert len(r.placements["p"]) == 1 and len(r.placements["q"]) == 1 and r.errors == {}


def test_copies_override_value():
    spec = build(p={"copies": {"type": "int", "value": 1}})
    assert len(evaluate(spec, {"p": {"copies": 4}}).placements["p"]) == 5


def test_copy_failure_only_affects_that_copy_and_is_reported():
    spec = build(p={"copies": {"type": "int", "value": 3}, "x": L(value=-1, formula="=10/(copy-2)")})
    r = evaluate(spec, {})
    assert [p.x for p in r.placements["p"]] == [-5.0, -10.0, -1.0, 10.0]
    assert ("p", "x") in r.errors and "Copy 2" in r.errors[("p", "x")]


def test_copy_failure_uses_last():
    spec = build(p={"copies": {"type": "int", "value": 1}, "x": L(value=-1, formula="=1/(copy-1)")})
    r = evaluate(spec, {}, {"p": {"x": 4}})
    assert [p.x for p in r.placements["p"]] == [-1.0, 4.0]


def test_many_copies_fast():
    spec = build({}, **{f"p{i}": {"copies": {"type": "int", "value": 200}, "x": L(formula="=copy*2")}
                        for i in range(5)})
    start = time.perf_counter()
    r = evaluate(spec, {})
    assert time.perf_counter() - start < 1.0
    assert len(r.placements["p4"]) == 201 and r.placements["p4"][200].x == 400.0


def test_copies_cyclic_attr_stays_fallback():
    spec = build(p={"copies": {"type": "int", "value": 2}, "x": L(value=3, formula="=x+copy")})
    r = evaluate(spec, {})
    assert [p.x for p in r.placements["p"]] == [3.0, 3.0, 3.0]
    assert ("p", "x") in r.errors


def test_material_and_rotation_fields():
    spec = build(p={"material": {"type": "material", "formula": '="Oak"'},
                    "rotz": {"type": "float", "formula": "=90"}})
    pl = evaluate(spec, {}).placements["p"][0]
    assert pl.material == "Oak" and pl.rotz == 90.0 and pl.rotx is None


def test_show_if_is_evaluated_and_fails_open():
    spec = build({
        "mode": {"type": "string", "value": "auto"},
        "count": {"type": "int", "value": 3, "show_if": '=Mode="fixed"'},
        "gap": L(value=0.3, show_if="=Mode=\"auto\""),
        "broken": L(value=1, show_if="=Ghost > 1"),
        "plain": L(value=2)})
    r = evaluate(spec, {})
    assert r.visible == {("", "count"): False, ("", "gap"): True, ("", "broken"): True}
    assert "Show if" in r.errors[("", "broken")]
    assert r.values[""]["broken"] == 1.0                     # values untouched
    r = evaluate(spec, {"": {"mode": "fixed"}})
    assert r.visible[("", "count")] is True and r.visible[("", "gap")] is False


def test_show_if_on_a_part_reads_its_own_attributes():
    spec = build({"on": {"type": "bool", "value": False}},
                 leaf={"x": L(value=1, show_if="=Parent!On")})
    assert evaluate(spec, {}).visible[("leaf", "x")] is False


def test_errors_are_messages():
    spec = build({"a": L(formula="=1/0")}, p={"x": L(formula="=1/(Copy-2)"),
                                               "copies": {"type": "int", "formula": "=3"}})
    r = evaluate(spec, {})
    assert r.errors[("", "a")].template == "Division by zero"
    copy_error = r.errors[("p", "x")]
    assert copy_error.template == "Copy {index}: {error}" and copy_error.params["index"] == 2
