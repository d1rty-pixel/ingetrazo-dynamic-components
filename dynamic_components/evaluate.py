"""Evaluate a dynamic-component spec into values and part placements."""
from __future__ import annotations

from dataclasses import dataclass, field

from . import formula as fm
from . import spec as sp
from .messages import Msg, text_of

# Formulas of all attributes and copies together may not exceed this many steps.
TOTAL_BUDGET = 1_000_000
_ROOT_WINS = frozenset({"x", "y", "z", "lenx", "leny", "lenz"})
_AXES = {"lenx": 0, "leny": 1, "lenz": 2}
_NUMERIC_OR_BOOL = ("length", "float", "int", "bool")
_PLACEMENT_FIELDS = ("x", "y", "z", "rotx", "roty", "rotz",
                     "lenx", "leny", "lenz", "hidden", "material")


@dataclass
class Placement:
    copy: int
    x: float | None = None
    y: float | None = None
    z: float | None = None
    rotx: float | None = None
    roty: float | None = None
    rotz: float | None = None
    lenx: float | None = None
    leny: float | None = None
    lenz: float | None = None
    hidden: bool | None = None
    material: str | None = None


@dataclass
class Result:
    values: dict[str, dict[str, object]]
    placements: dict[str, list[Placement]]
    errors: dict[tuple[str, str], str]
    visible: dict[tuple[str, str], bool] = field(default_factory=dict)


def evaluate(spec: dict, overrides: dict[str, dict[str, object]],
             last: dict[str, dict[str, object]] | None = None,
             *, max_copies: int = 1000) -> Result:
    """Evaluate `spec` with instance `overrides`; fail closed to `last`, then `value`."""
    return _Engine(sp.normalize(spec), overrides, last, max_copies).run()


def _lower_map(raw) -> dict:
    """node -> attr -> value with lower-case keys; malformed input is ignored."""
    result = {}
    if not isinstance(raw, dict):
        return result
    for node, attrs in raw.items():
        if isinstance(node, str) and isinstance(attrs, dict):
            result[node.lower()] = {str(k).lower(): v for k, v in attrs.items()}
    return result


def _sccs(keys, deps):
    """Iterative Tarjan; components come out dependencies first."""
    index, low, stack, on_stack, out = {}, {}, [], set(), []
    for start in keys:
        if start in index:
            continue
        index[start] = low[start] = len(index)
        stack.append(start)
        on_stack.add(start)
        work = [(start, iter(deps[start]))]
        while work:
            v, it = work[-1]
            for w in it:
                if w not in index:
                    index[w] = low[w] = len(index)
                    stack.append(w)
                    on_stack.add(w)
                    work.append((w, iter(deps[w])))
                    break
                if w in on_stack:
                    low[v] = min(low[v], index[w])
            else:
                work.pop()
                if work:
                    parent = work[-1][0]
                    low[parent] = min(low[parent], low[v])
                if low[v] == index[v]:
                    out.append(_pop_component(stack, on_stack, v))
    return out


def _pop_component(stack, on_stack, root):
    comp = []
    while True:
        w = stack.pop()
        on_stack.discard(w)
        comp.append(w)
        if w == root:
            return comp


class _Ctx:
    """Evaluation context: which part is being copied and its per-copy values."""

    def __init__(self, node=None, index=0, vals=None):
        self.node = node
        self.index = index
        self.vals = vals if vals is not None else {}


class _Engine:
    def __init__(self, spec, overrides, last, max_copies):
        self.nodes = spec["nodes"]
        self.overrides = _lower_map(overrides)
        self.last = _lower_map(last)
        self.max_copies = max(0, int(max_copies))
        self.budget_left = TOTAL_BUDGET
        self.errors: dict[tuple[str, str], str] = {}
        self.vals: dict[tuple[str, str], object] = {}
        self.attrs = self._collect_attrs()
        self.over: dict[tuple[str, str], object] = {}
        self.formulas: dict[tuple[str, str], fm.Formula] = {}
        self.deps: dict[tuple[str, str], list] = {}
        self.order: list = []
        self.cyclic: set = set()
        self._affected_cache: dict[str, list] = {}

    # -- setup

    def _collect_attrs(self) -> dict:
        attrs = {(n, a): attr for n, data in self.nodes.items()
                 for a, attr in data["attrs"].items()}
        size = self.nodes[""]["rest"].get("size")
        if size is not None:
            for name in _AXES:
                attrs.setdefault(("", name), {
                    "label": name, "type": "length", "value": None,
                    "formula": None, "access": "none"})
        return attrs

    def _root_wins(self, key) -> bool:
        return key[0] == "" and key[1] in _ROOT_WINS and key in self.over

    def _load_overrides(self) -> None:
        for key, attr in self.attrs.items():
            raw = self.overrides.get(key[0], {})
            if key[1] not in raw:
                continue
            if attr["formula"] and not (key[0] == "" and key[1] in _ROOT_WINS):
                continue
            try:
                self.over[key] = sp.coerce(attr, raw[key[1]])
            except sp.SpecError as exc:
                self.errors[key] = Msg("Ignored invalid stored value: {error}", error=text_of(exc))

    def _parse_formulas(self) -> None:
        for key, attr in self.attrs.items():
            if not attr["formula"] or self._root_wins(key):
                continue
            try:
                self.formulas[key] = fm.parse(attr["formula"])
            except fm.FormulaError as exc:
                self.errors[key] = text_of(exc)
                self.vals[key] = self._fallback(key)

    # -- values

    def _base(self, key):
        value = self.attrs[key]["value"]
        if value is None:
            size = self.nodes[key[0]]["rest"].get("size")
            return size[_AXES[key[1]]] if size is not None and key[1] in _AXES else 0.0
        return value

    def _fallback(self, key):
        raw = self.last.get(key[0], {}).get(key[1])
        if raw is not None:
            try:
                return sp.coerce(self.attrs[key], raw)
            except sp.SpecError:
                pass
        return self._base(key)

    def _resolve(self, token: str, current: str):
        if token == "self":
            return current
        if token == "parent":
            if current == "":
                raise fm.FormulaError(Msg("The component itself has no parent"))
            return ""
        if token and token in self.nodes:
            return token
        raise fm.FormulaError(Msg("Unknown part {part}", part=repr(token)))

    def _lookup(self, current: str, token: str, attr: str, ctx: _Ctx):
        target = self._resolve(token, current)
        if attr == "copy":
            return ctx.index if target == ctx.node else 0
        key = (target, attr)
        if key not in self.attrs:
            shown = attr if token == "self" else f"{token}!{attr}"
            raise fm.FormulaError(Msg("Unknown attribute {attr}", attr=repr(shown)))
        if target == ctx.node and key in ctx.vals:
            return ctx.vals[key]
        if key not in self.vals:
            raise fm.FormulaError(Msg("Attribute {attr} is not available", attr=repr(attr)))
        return self.vals[key]

    def _compute(self, key, ctx: _Ctx):
        attr = self.attrs[key]
        if self.budget_left <= 0:
            raise fm.FormulaError(Msg("Total evaluation budget exceeded"))

        def lookup(token, name):
            return self._lookup(key[0], token, name, ctx)

        budget = min(fm.DEFAULT_BUDGET, self.budget_left)
        try:
            value, used = fm.run(self.formulas[key], lookup, budget=budget)
        except fm.FormulaError as exc:
            self.budget_left -= exc.steps
            raise
        self.budget_left -= used
        return self._coerce_result(attr, value)

    @staticmethod
    def _coerce_result(attr, value):
        if isinstance(value, str) and attr["type"] in _NUMERIC_OR_BOOL:
            raise fm.FormulaError(Msg("Text result {value} cannot be used as {type}",
                                      value=repr(value[:30]), type=attr["type"]))
        try:
            return sp.coerce(attr, value)
        except sp.SpecError as exc:
            raise fm.FormulaError(exc.msg) from None

    # -- graph

    def _build_graph(self) -> None:
        for key, formula in self.formulas.items():
            deps = []
            for token, attr in formula.refs:
                try:
                    target = self._resolve(token, key[0])
                except fm.FormulaError:
                    continue
                if (target, attr) in self.formulas:
                    deps.append((target, attr))
            self.deps[key] = deps

    def _evaluate_all(self) -> None:
        for key, attr in self.attrs.items():
            if key not in self.formulas and key not in self.vals:
                self.vals[key] = self.over.get(key, self._base(key))
        ctx = _Ctx()
        for comp in _sccs(list(self.formulas), self.deps):
            if len(comp) > 1 or comp[0] in self.deps[comp[0]]:
                for key in comp:
                    self.cyclic.add(key)
                    self.errors[key] = Msg("Circular reference between attributes")
                    self.vals[key] = self._fallback(key)
                continue
            key = comp[0]
            self.order.append(key)
            try:
                self.vals[key] = self._compute(key, ctx)
            except fm.FormulaError as exc:
                self.errors[key] = text_of(exc)
                self.vals[key] = self._fallback(key)

    # -- copies

    def _affected(self, part: str) -> list:
        """Own attributes of `part` that depend on `copy`, dependencies first."""
        if part in self._affected_cache:
            return self._affected_cache[part]
        affected: set = set()
        result = []
        for key in self.order:
            if key[0] != part or key[1] == "copies":
                continue
            direct = any(a == "copy" and t in ("self", part)
                         for t, a in self.formulas[key].refs)
            if direct or any(d in affected for d in self.deps[key]):
                affected.add(key)
                result.append(key)
        self._affected_cache[part] = result
        return result

    def _copy_count(self, part: str) -> int:
        raw = self.vals.get((part, "copies"))
        if raw is None:
            return 0
        count = max(0, min(int(raw), self.max_copies))
        if count != raw:
            self.errors.setdefault(
                (part, "copies"), Msg("Copies limited to 0..{limit} (got {got})",
                                      limit=self.max_copies, got=raw))
        return count

    def _placement(self, part: str, index: int, vals: dict) -> Placement:
        fields = {name: vals.get((part, name)) for name in _PLACEMENT_FIELDS
                  if (part, name) in self.attrs}
        return Placement(copy=index, **fields)

    def _placements(self, part: str) -> list[Placement]:
        own = {k: v for k, v in self.vals.items() if k[0] == part}
        result = [self._placement(part, 0, own)]
        affected = self._affected(part)
        for index in range(1, self._copy_count(part) + 1):
            ctx = _Ctx(part, index, dict(own))
            for key in affected:
                self._compute_copy(key, ctx)
            result.append(self._placement(part, index, ctx.vals))
        return result

    def _compute_copy(self, key, ctx: _Ctx) -> None:
        try:
            ctx.vals[key] = self._compute(key, ctx)
        except fm.FormulaError as exc:
            ctx.vals[key] = self._fallback(key)
            self.errors.setdefault(key, Msg("Copy {index}: {error}", index=ctx.index,
                                            error=text_of(exc)))

    # -- driver

    def run(self) -> Result:
        self._load_overrides()
        self._parse_formulas()
        self._build_graph()
        self._evaluate_all()
        placements = {part: self._placements(part) for part in self.nodes if part}
        values: dict[str, dict[str, object]] = {node: {} for node in self.nodes}
        for (node, name), value in self.vals.items():
            values[node][name] = value
        return Result(values, placements, self.errors, self._visibility())

    # -- options layout

    def _visibility(self) -> dict:
        """show_if of every attribute that has one; a failing one shows the
        row (fail open) and reports why."""
        visible = {}
        for key, attr in self.attrs.items():
            source = attr.get("show_if")
            if not source:
                continue
            try:
                parsed = fm.parse(source)
                ctx = _Ctx()

                def lookup(token, name, _node=key[0]):
                    return self._lookup(_node, token, name, ctx)

                budget = min(fm.DEFAULT_BUDGET, max(self.budget_left, 0))
                if budget <= 0:
                    raise fm.FormulaError(Msg("Total evaluation budget exceeded"))
                value, used = fm.run(parsed, lookup, budget=budget)
                self.budget_left -= used
                visible[key] = bool(sp.coerce({"type": "bool"}, value))
            except (fm.FormulaError, sp.SpecError) as exc:
                self.budget_left -= getattr(exc, "steps", 0)
                visible[key] = True
                self.errors.setdefault(key, Msg("Show if: {error}", error=text_of(exc)))
        return visible
