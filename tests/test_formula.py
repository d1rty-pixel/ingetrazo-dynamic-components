import math
import time

import pytest

from dynamic_components import formula
from dynamic_components.formula import FormulaError, evaluate, parse


def run(src, env=None, **kw):
    env = {k.lower(): v for k, v in (env or {}).items()}

    def lookup(node, attr):
        key = attr if node == "self" else f"{node}!{attr}"
        if key not in env:
            raise FormulaError(f"unknown {key}")
        return env[key]

    return evaluate(parse(src), lookup, **kw)


def fails(src, env=None, **kw):
    with pytest.raises(FormulaError) as exc:
        run(src, env, **kw)
    assert str(exc.value)
    return str(exc.value)


@pytest.mark.parametrize("src,expected", [
    ("=1+2*3", 7.0), ("1+2*3", 7.0), ("=(1+2)*3", 9.0), ("=10/4", 2.5),
    ("=2^3^2", 512.0), ("=-2^2", 4.0), ("=2^-1", 0.5), ("=-(3)", -3.0),
    ("=1-2-3", -4.0), ("=8/2/2", 2.0), ("=+5", 5.0), ("=.5+1.", 1.5),
    ("=1e3", 1000.0), ("=2*3+4*5", 26.0),
])
def test_arithmetic(src, expected):
    assert run(src) == expected


@pytest.mark.parametrize("src,expected", [
    ("=1=1", True), ("=1<>2", True), ("=1<2", True), ("=2<=2", True),
    ("=3>2", True), ("=2>=3", False), ('="A"="a"', True), ('="a"<"b"', True),
    ("=TRUE=1", True), ("=FALSE<TRUE", True), ('=1<"a"', True), ('=1="1"', False),
    ("=1+1=2", True),
])
def test_comparison(src, expected):
    assert run(src) is expected


def test_concat_and_text():
    assert run('="a"&"b"&1') == "ab1"
    assert run('=1+1&"x"') == "2x"
    assert run('="it""s"') == 'it"s'
    assert run("='it''s'") == "it's"
    assert run("=TRUE&1.5") == "TRUE1.5"


def test_booleans():
    assert run("=TRUE") is True
    assert run("=false") is False
    assert run("=TRUE+TRUE") == 2.0
    assert run("=AND(TRUE, 1, 2>1)") is True
    assert run("=OR(FALSE, 0)") is False
    assert run("=NOT(0)") is True
    assert run('=IF("true", 1, 2)') == 1.0
    fails('=IF("maybe", 1, 2)')


def test_references_case_insensitive():
    env = {"LenX": 2.0, "Door!Width": 3.0, "parent!lenx": 5.0}
    assert run("=lenx*2", env) == 4.0
    assert run("=LENX + DOOR!width", env) == 5.0
    assert run("=Parent!LenX", env) == 5.0
    f = parse("=LenX + Parent!LenZ + Leaf!X + Self!Y")
    assert f.refs == {("self", "lenx"), ("parent", "lenz"), ("leaf", "x"), ("self", "y")}


def test_ref_types_sanitized():
    assert run("=a+1", {"a": 4}) == 5.0
    assert run("=a", {"a": True}) is True
    fails("=a", {"a": None})
    fails("=a", {"a": [1]})
    fails("=a", {"a": float("inf")})
    fails("=a", {"a": 10 ** 400})
    fails("=a", {"a": "x" * 70000})
    assert run("=a", {"a": "x" * 100}) == "x" * 100


def test_lookup_errors_become_formula_errors():
    fails("=missing")

    def boom(node, attr):
        raise KeyError("x")

    with pytest.raises(FormulaError):
        evaluate(parse("=a"), boom)


def test_if_lazy():
    assert run("=IF(1, 5, 1/0)") == 5.0
    assert run("=IF(0, 1/0, 6)") == 6.0
    assert run("=IF(0, 1)") is False
    seen = []

    def lookup(node, attr):
        seen.append(attr)
        return 1.0

    evaluate(parse("=IF(a>0, b, c)"), lookup)
    assert seen == ["a", "b"]
    assert run("=CHOOSE(2, 1/0, 7, 1/0)") == 7.0


def test_choose_errors():
    fails("=CHOOSE(0, 1, 2)")
    fails("=CHOOSE(3, 1, 2)")
    fails("=CHOOSE(1)")
    assert run("=CHOOSE(1.9, 10, 20)") == 10.0


@pytest.mark.parametrize("src,expected", [
    ("=MIN(3,1,2)", 1.0), ("=MAX(3,1,2)", 3.0), ("=ABS(-4)", 4.0),
    ("=ROUND(2.5)", 3.0), ("=ROUND(-2.5)", -3.0), ("=ROUND(2.675, 2)", 2.68),
    ("=ROUND(1234, -2)", 1200.0), ("=FLOOR(2.7)", 2.0), ("=CEILING(2.1)", 3.0),
    ("=FLOOR(0.3, 0.1)", 0.3), ("=CEILING(0.01, 0.05)", 0.05),
    ("=INT(-2.5)", -3.0), ("=SQRT(16)", 4.0), ("=SIN(90)", 1.0),
    ("=COS(180)", -1.0), ("=SIN(180)", 0.0), ("=TAN(45)", 1.0),
    ("=ASIN(1)", 90.0), ("=ACOS(0)", 90.0), ("=ATAN(1)", 45.0),
    ("=RADIANS(180)", math.pi), ("=DEGREES(PI())", 180.0), ("=PI()", math.pi),
    ("=LEN(\"abc\")", 3.0), ("=LEFT(\"abcdef\", 2)", "ab"), ("=LEFT(\"abc\")", "a"),
    ("=RIGHT(\"abcdef\", 2)", "ef"), ("=RIGHT(\"abc\", 0)", ""),
    ("=MID(\"abcdef\", 2, 3)", "bcd"), ("=CONCATENATE(\"a\", 1, TRUE)", "a1TRUE"),
    ("=VALUE(\"3.5\")", 3.5), ("=LOWER(\"AbC\")", "abc"), ("=UPPER(\"AbC\")", "ABC"),
    ("=TRIM(\"  a   b  \")", "a b"), ("=len(12.5)", 4.0),
])
def test_functions(src, expected):
    result = run(src)
    if isinstance(expected, float):
        assert result == pytest.approx(expected)
    else:
        assert result == expected


@pytest.mark.parametrize("src", [
    "=1/0", "=5/(2-2)", "=0^-1", "=(-8)^0.5", "=SQRT(-1)", "=ASIN(2)", "=ACOS(-2)",
    "=TAN(90)", "=10^400", "=10^308*10", "=FLOOR(1,0)", "=LEFT(\"a\",-1)",
    "=MID(\"abc\",0,1)", "=VALUE(\"abc\")", "=VALUE(\"inf\")", "=VALUE(\"nan\")",
    "=VALUE(\"1_000\")", '="a"+1', '=-"a"', "=FOO(1)", "=IF()", "=IF(1,2,3,4)",
    "=ABS()", "=ABS(1,2)", "=PI(1)", "=MIN()", "=ROUND(1,2,3)", "=NOT()",
])
def test_runtime_errors(src):
    fails(src)


@pytest.mark.parametrize("src", [
    "", "=", "  = ", "==1", "=1+", "=(1", "=1)", "=1 2", "=,", "=IF(1,)", "=IF(,1)",
    "=1,2", "=a!", "=!a", "=a!1", "=1!a", '="abc', "=1 $ 2", "=a.b", "=1e", "=2x",
    "=;", "=ABS(1,", "=#REF!", "=a b", "=Parent!", "=x[1]", "=x{1}", "=1 = = 1",
])
def test_syntax_errors(src):
    with pytest.raises(FormulaError):
        parse(src)


def test_leading_equals_optional_and_whitespace():
    assert run("  =  1 + 1  ") == 2.0
    assert run("1+1") == 2.0
    assert parse("=a").source == "=a"


def test_non_string_source():
    with pytest.raises(FormulaError):
        parse(None)
    with pytest.raises(FormulaError):
        parse(5)


@pytest.mark.parametrize("src", [
    "=__import__('os').system('id')", "=__import__('os')", "=eval('1')",
    "=exec('x')", "=open('/etc/passwd')", "=().__class__", "=a.__class__",
    "=[x for x in 1]", "=lambda: 1", "=a if b else c", "=print(1)", "=compile('1','','eval')",
    "=getattr(a,'b')", "=a;b", "=1\n__import__('os')",
])
def test_python_injection_is_inert(src):
    try:
        run(src, {"a": 1.0, "b": 2.0, "c": 3.0})
    except FormulaError:
        return
    pytest.fail("expected FormulaError")


def test_injection_text_is_just_a_string():
    assert run("=\"__import__('os')\"") == "__import__('os')"


def test_unknown_function_message_names_it():
    assert "FOO" in fails("=foo(1)")
    assert "ABS" in fails("=abs()")


def test_limit_source_length():
    assert run("=" + "1+" * 2000 + "1") == 2001.0
    with pytest.raises(FormulaError):
        parse("=" + "1" * 4096)
    with pytest.raises(FormulaError):
        parse("=" + "1+" * 2049 + "1")


def test_limit_nesting_depth():
    assert run("=" + "(" * 60 + "1" + ")" * 60) == 1.0
    for src in ("=" + "(" * 65 + "1" + ")" * 65, "=" + "-" * 100 + "1",
                "=" + "ABS(" * 70 + "1" + ")" * 70, "=" + "2^" * 100 + "2",
                "=" + "(" * 2000 + "1" + ")" * 2000):
        with pytest.raises(FormulaError, match="nested"):
            parse(src)


def test_limit_arguments():
    assert run("=MAX(" + ",".join(["1"] * 64) + ")") == 1.0
    with pytest.raises(FormulaError, match="Too many"):
        parse("=MAX(" + ",".join(["1"] * 65) + ")")


def test_huge_numbers():
    for src in ("=1e999", "=" + "9" * 400, "=1e309", "=.5e999"):
        with pytest.raises(FormulaError):
            parse(src)
    fails("=1e308*10")
    fails("=1e308+1e308")
    assert run("=1e308") == 1e308


def test_string_cap():
    fails('=CONCATENATE(' + ",".join(['"' + "x" * 3000 + '"'] * 30) + ")")
    big = "x" * 40000
    fails("=a&a", {"a": big})
    assert len(run("=a&a", {"a": "x" * 30000})) == 60000


def test_budget_exhaustion():
    fails("=" + "1+" * 50 + "1", budget=20)
    nested = "=" + "IF(1," * 30 + "1" + ",0)" * 30
    fails(nested, budget=50)
    assert run(nested) == 1.0
    choose = "=" + "CHOOSE(1," * 30 + "1" + ",0)" * 30
    fails(choose, budget=50)


def test_default_budget_stops_long_formula_quickly():
    src = "=" + "IF(1," * 10 + "1" + ",0)" * 10
    start = time.perf_counter()
    for _ in range(20):
        run(src)
    assert time.perf_counter() - start < 1.0


def test_steps_reported():
    value, used = formula.run(parse("=1+2"), lambda n, a: 0)
    assert value == 3.0 and used > 0
    with pytest.raises(FormulaError) as exc:
        formula.run(parse("=1+2+3+4"), lambda n, a: 0, budget=3)
    assert exc.value.steps > 3


def test_number_text_formatting():
    assert run('=1.5&""') == "1.5"
    assert run('=100&""') == "100"
    assert run('=0.1+0.2&""') == "0.3"


def test_returns_only_plain_types():
    for src in ("=1", '="a"', "=1=1", "=PI()", "=LEN(\"a\")"):
        assert type(run(src)) in (float, str, bool)
