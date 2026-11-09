# Module contract

The interfaces between the modules of `dynamic_components/`. Design rationale is in
[DESIGN.md](DESIGN.md); this file is the binding agreement between modules. A module
may add private helpers freely, but changes to anything listed here are changes to
this file first.

Layers, strictly one-way:

```
formula.py   pure Python, no Qt, no IngeTrazo imports
spec.py      pure Python, no Qt, no IngeTrazo imports
evaluate.py  pure Python, no Qt, no IngeTrazo imports      (uses formula, spec)
binding.py   IngeTrazo model + PySide6.QtGui math           (uses spec, evaluate)
ui/*.py      PySide6 widgets                                (uses spec, binding)
__init__.py  setup(app): menus, context menu, hooks          (uses binding, ui)
```

## Conventions

- Attribute names are **case-insensitive**; every dict key holding an attribute name
  is lower case. The display name is kept in the attribute's `label`.
- Units inside the engine: lengths in **metres**, angles in **degrees**.
- Reserved attribute names (meaning fixed by the engine):
  `x y z lenx leny lenz rotx roty rotz hidden material copies` and the read-only
  `copy` (index of a generated copy, 0 for the original).
- Node names: `""` (empty string) is the component itself (the root); every other node
  is a part, named by its part name (lower case, unique within the definition).
- All spec and state data is JSON-safe (dicts, lists, str, int, float, bool, None).

## formula.py

```python
class FormulaError(Exception): ...         # message is user-facing English text

class Formula:
    source: str                             # as written, e.g. '=IF(LenX>1, 2, 1)'
    refs: frozenset[tuple[str, str]]        # (node, attr) it reads; node is
                                            #   "self", "parent" or a sibling part name

def parse(source: str) -> Formula           # raises FormulaError (syntax, limits)
def run(f: Formula, lookup, *, budget: int = 10_000) -> tuple[object, int]
    # evaluate() plus the steps used; a FormulaError carries `.steps`. Text
    # results cost extra steps by length.
def evaluate(f: Formula, lookup, *, budget: int = 10_000) -> object
    # lookup(node: str, attr: str) -> value; may raise FormulaError.
    # Returns float | str | bool. Raises FormulaError on any runtime error,
    # including budget exhaustion. Never raises anything else.
```

Syntax (SketchUp-compatible surface): optional leading `=`; numbers; `"strings"`;
`+ - * / ^`, unary `-`; `& ` string concatenation; comparisons `= <> < > <= >=`;
`AND(…)`, `OR(…)`, `NOT(…)` as functions; references `Name`, `Parent!Name`,
`PartName!Name`; function calls `NAME(arg, …)`. Function set, at least: `IF, AND, OR,
NOT, MIN, MAX, ABS, ROUND, FLOOR, CEILING, INT, SQRT, SIN, COS, TAN, ASIN, ACOS, ATAN,
RADIANS, DEGREES, PI, CHOOSE, LEN, LEFT, RIGHT, MID, CONCATENATE, VALUE, LOWER, UPPER,
TRIM`. Trig works in degrees like SketchUp. Limits: source ≤ 4096 characters, nesting
depth ≤ 64, call arguments ≤ 64, evaluation step budget. No Python `eval`, no `ast`
compile, no attribute access.

## spec.py

Definition spec (one entry of the registry):

```json
{
  "version": 1,
  "name": "Door",
  "nodes": {
    "":     {"attrs": {"width": {...attr...}}, "rest": {"size": [lx, ly, lz]}},
    "leaf": {"label": "Leaf", "attrs": {"lenx": {...}, "x": {...}},
             "rest": {"xform": [16 floats, column-major as QMatrix4x4.data()],
                      "size": [lx, ly, lz]}}
  }
}
```

Attribute:

```json
{"label": "Width", "type": "length", "value": 0.9, "formula": null,
 "access": "textbox", "options": [["Narrow", 0.8], ["Wide", 1.0]],
 "min": 0.6, "max": 1.2}
```

- `type`: `length | float | int | bool | string | choice | material`
- `value`: the default (used when there is no formula and no instance override)
- `formula`: source text or `null`
- `access`: `none` (hidden from users) | `view` | `textbox` | `list` (uses `options`)
- `options`, `min`, `max`: optional

```python
class SpecError(Exception): ...

def normalize(spec: dict) -> dict           # validated, lower-cased deep copy;
                                            # raises SpecError; enforces limits
                                            # (≤ 256 nodes, ≤ 256 attrs per node)
def coerce(attr: dict, value) -> object     # value converted to attr["type"]
                                            # (clamped to min/max); raises SpecError
def editable_attrs(spec: dict) -> list[tuple[str, str, dict]]
                                            # (node, name, attr) with access in
                                            # {textbox, list}, root first, stable order
RESERVED: frozenset[str]
```

## evaluate.py

```python
@dataclass
class Placement:
    copy: int                               # 0 = the part itself, 1..n generated
    x: float | None; y: float | None; z: float | None      # None = keep rest
    rotx: float | None; roty: float | None; rotz: float | None
    lenx: float | None; leny: float | None; lenz: float | None
    hidden: bool | None
    material: str | None

@dataclass
class Result:
    values: dict[str, dict[str, object]]    # node -> attr -> value (copy 0)
    placements: dict[str, list[Placement]]  # part node -> one per copy (len = copies+1)
    errors: dict[tuple[str, str], str]      # (node, attr) -> message

def evaluate(spec: dict, overrides: dict[str, dict[str, object]],
             last: dict[str, dict[str, object]] | None = None,
             *, max_copies: int = 1000) -> Result
```

- `overrides`: instance values, node -> attr -> value. An override wins over
  `value` but **not** over a formula (SketchUp semantics: a formula attribute
  shows its computed value). Exception: `lenx/leny/lenz/x/y/z` overrides on the
  root, which come from the user scaling or moving the instance, win.
- Root `lenx/leny/lenz` default to the root's rest size when not set.
- Dependency order across all nodes; `parent` of a part is the root (one level
  of parts for now); sibling references by part name.
- **Fail closed:** an attribute whose formula fails, cycles or exceeds the budget
  gets its value from `last` if present, otherwise its `value`; the error is
  reported in `errors`. Never raises for formula problems; raises `SpecError`
  only for a spec that does not normalize.
- `copies` is clamped to `0..max_copies` (clamping is reported in `errors`).
  For copy `i`, `copy` evaluates to `i` and only that part's own attributes are
  re-evaluated per copy.

## binding.py

Document data: `scene.plugin_data["dynamic_components"]` =
`{"version": 1, "defs": {def_id: spec}}` (written only through `DynamicCommand`).

On groups, `group.ext["dynamic_components"]`:

- instance root: `{"def": def_id, "set": {node: {attr: value}}, "last": {...}}`
- part (child of the root): `{"part": name}`; generated copy: `{"part": name, "copy": i}`

```python
KEY = "dynamic_components"

def registry(scene) -> dict                 # read-only view, {} when none
def definition(scene, group) -> dict | None # normalized spec of a dynamic instance
def is_dynamic(group) -> bool
def instances_of(scene, def_id) -> list     # every root group using def_id, any depth

def make_dynamic(scene, group, spec=None) -> str
    # Turn a component instance into a dynamic one: assigns part names to its
    # children (from their names, made unique), records each part's rest xform
    # and size, stores the spec (a minimal one when None) and returns def_id.
    # Mutates; call inside DynamicCommand.
def apply(scene, group) -> Result
    # Evaluate and write the result into the group's children: xform, hidden,
    # material, generated copies (added/removed as needed, sharing the part's
    # prototype mesh). Mutates; call inside DynamicCommand.
def set_values(scene, group, values: dict[str, dict[str, object]]) -> Result
    # Store overrides (coerced) then apply. Mutates; inside DynamicCommand.
def set_definition(scene, def_id, spec) -> None
    # Replace a spec and re-apply every instance. Mutates; inside DynamicCommand.
def absorb_scale(scene, group) -> bool
    # If the root's xform carries a scale ≠ 1 on an axis that the spec uses
    # (some formula reads parent!len<axis> or the root's own len<axis>), move
    # that axis' scale into the root lenx/leny/lenz override, normalise that
    # axis of the xform, apply. Other axes keep their scale. True if changed.
def absorbable_axes(scene, group) -> list[int]
    # The axes absorb_scale would take over; empty = it would do nothing, so
    # callers skip the undo step.
def bake(scene, group) -> None
    # Remove the dynamic records from the root and its parts (generated copies
    # become plain parts); geometry and placements stay as they are now.

class DynamicCommand(core.history.Command):
    def __init__(self, mutate, roots, label="Dynamic component"): ...
    # mutate(scene) does the work. Snapshots scene.groups, plugin_data[KEY] and,
    # for each root in `roots` (and, when a definition changes, every instance
    # of it) the whole subtree's xform/children/hidden/material/ext. One undo
    # step; a mutate that raises is rolled back and re-raised.
def run(viewport, mutate, roots, label=...) -> None
    # viewport.history.execute(DynamicCommand(mutate, roots, label));
    # viewport.notify_scene_changed(). Re-raises what mutate raised (the host's
    # History.execute only logs it); nothing is left on the undo stack then.
```

## ui/

```python
class OptionsDialog(QDialog):               # ui/options.py
    def __init__(self, app, group, parent=None)
    # One row per editable attribute (spec.editable_attrs), widgets by type and
    # access, errors from the last Result shown inline. Apply = binding.run(...
    # set_values ...) = one undo step.

class AttributesPanel(QWidget):             # ui/attributes.py
    def __init__(self, app)
    # Authoring: the selected dynamic instance's spec as a tree/table of nodes and
    # attributes (name, label, type, value, formula, access); edits go through
    # binding.run(... set_definition ...). refresh() on document change.
```

## __init__.py

```python
def setup(app):
    # api_version check (2); add_panel(AttributesPanel); add_context_menu:
    # "Make Dynamic" on a component instance, "Component Options…" and
    # "Bake Dynamic Component" on a dynamic one; add_outliner_kind;
    # on_document_changed -> absorb_scale for dynamic instances whose xform
    # carries a scale (re-entrancy guarded).
```
