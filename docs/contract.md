# Module contract

The interfaces between the modules of `dynamic_components/`. Design rationale is in
[DESIGN.md](DESIGN.md); this file is the binding agreement between modules. A module
may add private helpers freely, but changes to anything listed here are changes to
this file first.

Layers, strictly one-way:

```
messages.py  pure Python: translatable messages (Msg)
formula.py   pure Python, no Qt, no IngeTrazo imports      (uses messages)
spec.py      pure Python, no Qt, no IngeTrazo imports      (uses messages)
evaluate.py  pure Python, no Qt, no IngeTrazo imports      (uses formula, spec)
geometry.py  pure Python, no Qt, no IngeTrazo imports      (uses messages)
i18n.py      tr/N_/tr_msg; reads the host language lazily (uses messages)
generators.py IngeTrazo Mesh + PySide6.QtGui               (uses geometry)
binding.py   IngeTrazo model + PySide6.QtGui math           (uses spec, evaluate,
                                                            generators)
ui/*.py      PySide6 widgets                                (uses spec, binding)
__init__.py  setup(app): context menu, hooks                 (uses binding, ui)
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
- User-facing text from the pure modules is a `messages.Msg` (see below); every
  other user-facing string goes through `i18n.tr`.

## messages.py

```python
class Msg(str):
    # The English text (what str() and == see) that also remembers how it was
    # made, so the UI can translate it.
    template: str                           # English, with {named} fields
    params: dict[str, object]               # values; may be Msg themselves
    def __new__(cls, template: str, **params) -> Msg
    def to_json(self) -> dict               # {"t": template, "p": {...}}
    @classmethod
    def from_json(cls, data) -> Msg | None  # None for anything malformed

def text_of(exc) -> str                     # exc.msg if it has one, else str(exc)
```

`FormulaError`, `SpecError` and `GeometryError` take a `Msg` and keep it as `.msg`.

## formula.py

```python
class FormulaError(Exception): ...         # message is user-facing English text

class Formula:
    source: str                             # as written, e.g. '=IF(LenX>1, 2, 1)'
    refs: frozenset[tuple[str, str]]        # (node, attr) it reads; node is
                                            #   "self", "parent" or a sibling part name

FUNCTIONS: tuple[str, ...]                  # every callable function name, sorted

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
NOT, MIN, MAX, ABS, ROUND, FLOOR, CEILING, INT, MOD, SQRT, SIN, COS, TAN, ASIN, ACOS,
ATAN, RADIANS, DEGREES, PI, CHOOSE, LEN, LEFT, RIGHT, MID, CONCATENATE, VALUE, LOWER,
UPPER, TRIM`. `MOD(n, d)` = `n − d·INT(n/d)` (sign of `d`, as Excel); `d = 0` is an
error. Trig works in degrees like SketchUp. Limits: source ≤ 4096 characters, nesting
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
                      "size": [lx, ly, lz]}},
    "side": {"gen": "board@1", "attrs": {...}, "rest": {...}},
    "hole": {"cut": "side", "attrs": {...}, "rest": {...}}
  }
}
```

Node fields besides `label`, `attrs`, `rest` (parts only, never the root):

- `gen`: generator name `kind@version` (`^[a-z][a-z0-9_]*@[0-9]+$`). The part's mesh
  is built by that generator at the part's size instead of being stretched
  (DESIGN.md section 13). Whether the generator exists is the binding's question.
- `cut`: name of another part. This part is a cutter of that one; it must not be
  itself, the root, or a cutter, and must not have `gen` itself.
- `normalize` raises `SpecError` for a malformed `gen`, a root with `gen`/`cut` or a
  broken `cut` link.

Attribute:

```json
{"label": "Width", "type": "length", "value": 0.9, "formula": null,
 "access": "textbox", "options": [["Narrow", 0.8], ["Wide", 1.0]],
 "min": 0.6, "max": 1.2, "section": "Carcass", "show_if": "=Style=\"wide\""}
```

- `type`: `length | float | int | bool | string | choice | material`
- `value`: the default (used when there is no formula and no instance override)
- `formula`: source text or `null`
- `access`: `none` (hidden from users) | `view` | `textbox` | `list` (uses `options`)
  | `warn` (shown as a warning while the value is not empty/false/0)
- `options`, `min`, `max`: optional
- `section`: optional heading in the Options form (≤ 256 characters)
- `show_if`: optional formula; the Options row is shown only while it is true

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
    errors: dict[tuple[str, str], str]      # (node, attr) -> message (a Msg)
    visible: dict[tuple[str, str], bool]    # show_if of each attribute that has one

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
- `show_if` is evaluated after all values, in the context of its node (copy 0).
  A failing one counts as `True` (fail open) and its error is reported under the
  attribute as "Show if: …". It never changes a value.

## binding.py

Document data: `scene.plugin_data["dynamic_components"]` =
`{"version": 1, "defs": {def_id: spec}}` (written only through `DynamicCommand`).

On groups, `group.ext["dynamic_components"]`:

- instance root: `{"def": def_id, "set": {node: {attr: value}}, "last": {...},
  "spec": {...}, "problems": {node: [Msg.to_json(), …]}}` (`problems`: what
  generation reported at the last apply; absent when none). `spec` is a copy of the
  definition the instance was last written with, so the instance carries it into
  a document that has no such definition (paste, import); see `definition`.
- part (child of the root): `{"part": name}`; generated copy: `{"part": name, "copy": i}`
- a generated part or copy also carries `"gen": {"key": sha1, "lens": [lx, ly, lz],
  "anchor": [ax, ay, az], "fp": [faces, vertices], "paint": {...},
  "issues": [[cutter, Msg.to_json()], …]}`: the key and size the mesh was built
  for, the box origin as a fraction of the size, the mesh's fingerprint, the paint
  taken from the original mesh and what its cutters could not do
- a cutter part carries `"cutter": true` while it is hidden as one

```python
KEY = "dynamic_components"

def registry(scene) -> dict                 # read-only view, {} when none
def definition(scene, group) -> dict | None # normalized spec of a dynamic instance
    # The registry's entry for its def_id wins; when the document has none, the
    # instance's own `spec` copy is used (re-validated like any document data).
    # Neither valid -> None. Reads only.
def is_dynamic(group) -> bool
def instances_of(scene, def_id) -> list     # every root group using def_id, any depth

def make_dynamic(scene, group, spec=None, names=None) -> str
    # Turn a component instance into a dynamic one: assigns part names to its
    # children (from their names, made unique; `names`, a list parallel to
    # group.children, gives them explicitly), records each part's rest xform
    # and size, stores the spec (a minimal one when None) and returns def_id.
    # Mutates; call inside DynamicCommand.
def apply(scene, group) -> Result
    # Also refreshes the instance's `spec` copy from the definition it used and,
    # when the registry lacks that def_id, adopts the definition into it (the
    # registry's own entry is never overwritten this way). Every write of a
    # definition refreshes the `spec` of all its instances.
    # Evaluate and write the result into the group's children: xform, hidden,
    # material, generated copies (added/removed as needed, sharing the part's
    # prototype mesh). Parts with `gen` get a mesh from their generator at their
    # size, cut by the active placements of their cutters (DESIGN.md 13); their
    # xform carries no scale. A cutter cuts with its local bounding box: a
    # mesh of at most 6 faces (a box) cuts a rectangle, anything else (a
    # cylinder) a circle. Cutters are always hidden; a part that stops being
    # a cutter is shown again (record flag "cutter"). Problems go to the
    # instance's `problems`; a part edited by hand keeps its mesh (problem
    # "edited by hand"). Mutates; call inside DynamicCommand.
def regenerate(scene, group) -> int
    # Like apply, but also rebuilds generated parts edited by hand (their edits
    # are lost). Returns how many meshes were rebuilt. Mutates; DynamicCommand.
def problems(group) -> dict[str, list[Msg]]
    # The instance's stored generation problems, by part name.
def edited_parts(group) -> list[str]
    # Generated parts of this instance whose mesh no longer matches what was
    # generated (fingerprint).
def set_values(scene, group, values: dict[str, dict[str, object]]) -> Result
    # Store overrides (coerced) then apply; a value of None removes that
    # override (back to the default). Mutates; inside DynamicCommand.
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
def preview_scale(scene, group) -> bool
    # While a tool previews a scale (nothing committed yet): lay the parts out
    # for the size the root's xform scale stands for and cancel that scale in
    # the written parts, so boards keep their thickness during the drag. Writes
    # only placements (no overrides, no `last`, no undo step); the layout is a
    # function of xform + stored state, so undo/redo stay consistent. True if a
    # placement changed. Generated parts are not rebuilt: they are scaled from
    # the size their mesh was built for.
def relayout(scene, group) -> bool
    # Placements back to the stored state (after a preview was cancelled or its
    # scale undone); no undo step, no mesh rebuilt. True if a placement changed.
def loose_children(group) -> list
    # Children of a dynamic root that are no part yet (moved in from outside).
def add_parts(scene, group, only=None) -> list[str]
    # Register loose_children (or just those in `only`) as parts: unique part
    # name, rest xform and size, node in the definition. Mutates; inside
    # DynamicCommand.
def is_open(scene, group) -> bool
    # The host has `group` (or something inside it) open for editing
    # (scene.edit_group). Entering a container pushes its matrix down into its
    # children and leaves it at identity (core.scene._bake_container_xform),
    # and leaving does not undo that; while open, nothing is written.
def settle(scene, group) -> bool
    # After the host pushed the root's matrix down: read that matrix back from
    # the parts (the one most parts agree on, against the stored layout) and
    # pull it up into the root again; nothing moves in the world. No undo step
    # (the push-down had none). True if it changed something.
def present_parts(group) -> set[str]       # part names with geometry here
def missing_parts(scene, group) -> list[str]
    # Parts of the definition this instance has no group for (deleted here).
def remove_parts(scene, group, names) -> None
    # Drop those nodes from the definition; in other instances their groups
    # become loose children (kept, no longer parts). Mutates; DynamicCommand.
def dynamic_roots(scene) -> list            # every dynamic instance, any depth
def holder(scene, group)                    # the dynamic root `group` sits in
                                            # directly, else None
def add_problem(scene, groups, root) -> str | None
    # Why `groups` cannot be added to `root` (user-facing English), None when
    # they can: root not dynamic, a group is the root or a part already, or the
    # host's own rule (core.outliner.reparent_problem: cycle, component, locked).
def add_to_component(viewport, groups, root, label=...) -> list[str]
    # One undo step: the host's ReparentGroupsCommand (world placement kept)
    # into `root`, then add_parts(only=groups). Returns the new part names;
    # raises ValueError with add_problem's text.
def bake(scene, group) -> None
    # Remove the dynamic records from the root and its parts (generated copies
    # become plain parts); geometry and placements stay as they are now.
    # Cutter parts (tools, never drawn) and hidden parts (and hidden copies) are
    # removed.

class DynamicCommand(core.history.Command):
    def __init__(self, mutate, roots, label="Dynamic component"): ...
    # mutate(scene) does the work. Snapshots scene.groups, plugin_data[KEY] and,
    # for each root in `roots` (and, when a definition changes, every instance
    # of it) the whole subtree's xform/children/hidden/material/ext/mesh (the
    # mesh by reference: generation replaces meshes, never edits one). One undo
    # step; a mutate that raises is rolled back and re-raised.
def run(viewport, mutate, roots, label=...) -> None
    # viewport.history.execute(DynamicCommand(mutate, roots, label));
    # viewport.notify_scene_changed(). Re-raises what mutate raised (the host's
    # History.execute only logs it); nothing is left on the undo stack then.
```

## geometry.py

```python
Point = tuple[float, float, float]

ROUND, RECT, AUTO = "round", "rect", "auto"
EPS = 1e-6                                  # closer counts as touching (float32
                                            # matrices: ~2e-7 at 2 m)

@dataclass(frozen=True)
class Box:                                  # axis-aligned, lo < hi on every axis
    lo: Point
    hi: Point
    kind: str = AUTO                        # AUTO: round when the two sides
                                            # across the cut are equal

@dataclass
class Shape:                                # pure polygon data
    faces: list[tuple[list[Point], list[list[Point]]]]
        # (outer loop, hole loops); outer counter-clockwise seen from outside,
        # holes the other way round
    soft: list[tuple[Point, Point]]         # edges to draw soft (round walls)
    issues: list[tuple[int, Msg]]           # (index into cuts, why it was skipped)

class GeometryError(Exception): ...         # .msg; the whole shape failed

def segments_for(diameter: float) -> int    # 12 (≤ 10 mm), 24 (≤ 40 mm), else 32
def board(size: Point, origin: Point = (0, 0, 0), cuts: list[Box] = (), *,
          max_cuts=2000, max_faces=200_000) -> Shape
    # A box [origin, origin+size] with round holes / rectangular pockets cut
    # by `cuts` (DESIGN.md 13 for what is recognised). Unusable cuts are
    # skipped and listed in `issues`; GeometryError for a degenerate size or
    # exceeded limits.
```

## generators.py

```python
def register(name: str, build) -> None
    # build(size, origin, cuts, params) -> geometry.Shape; `name` "kind@n".
    # params: the part's evaluated attributes (attr -> value). ValueError for
    # a malformed name or a name already taken.
def known(name: str) -> bool
def build(name, size, origin, cuts, params) -> geometry.Shape
    # GeometryError (with a Msg) for an unknown name or anything the
    # generator raised.
def to_mesh(shape, paint=None) -> core.mesh.Mesh
    # Faces with holes, soft edges set, `paint` ({"color": …, "mat": …}) on
    # every face.
def cached(key) -> tuple[Mesh, issues] | None ; remember(key, (mesh, issues))
    # Session cache of generated meshes by key (bounded, 256 entries), with
    # the issues the build reported ([[cut index, Msg.to_json()], …]).
def fingerprint(mesh) -> list[int]          # [faces, vertices]
def clean_paint(attrs) -> dict              # color/mat/opacity, JSON-safe
def names() -> list[str]
```

Built in: `board@1` = `geometry.board`: holes and pockets inside a face, and
grooves (a rectangular cut that runs along the whole length of the board from one
face; the board becomes an extrusion of a profile with slots; all grooves of a board
run the same way from the same face, a groove may not reach the board's sides
across it).

## i18n.py

```python
def tr(text: str, /, **kwargs) -> str       # catalog lookup, then str.format
def N_(text: str) -> str                    # marks a constant for the catalogs
def tr_msg(message) -> str                  # a Msg translated (recursively);
                                            # plain text unchanged
def language() -> str                       # the host's, "en" outside it
```

Catalogs: `dynamic_components/locale/<lang>.json`, flat `{english: translation}`.
`en.json` holds only a `_comment` (English is the source); a missing catalog or
entry falls back to English, a regional tag (`fr-CA`) to its base language first.

## ui/

One side-tray tab, top to bottom: header, Options, one fold section per node,
Apply/Discard for definition edits. Lengths are shown and typed in the document's
length unit (`core.units`, read-only use of the host); everything stored stays in
metres.

```python
class DynamicPanel(QWidget):                # ui/panel.py
    def __init__(self, app)
    # Header: the component's name, part count, "Bake" (binding.run(... bake ...)).
    # Groups moved into the component that are no part yet: a note naming them
    # and "Add as part" (binding.run(... add_parts ...), not while the attribute
    # editor has unapplied changes). Parts deleted here: not shown, a note and
    # "Remove from definition". Nothing selected while the host has a dynamic
    # component open for editing: that component is shown, read-only, with a
    # note to leave it first (is_open).
    # Generated parts edited by hand (binding.edited_parts): a note and
    # "Regenerate" (binding.run(... regenerate ...)).
    # Without a dynamic selection: a hint, and "Make Dynamic" for one plain
    # component instance. refresh() on document change: rebuilds only when the
    # selection, the definition or its structure changed, otherwise updates
    # values in place (a field being typed in keeps its focus).
    def refresh() -> None
    def show_options() -> None              # unfold Options, scroll to the top

class OptionsForm(QWidget):                 # ui/options.py
    def __init__(self, app)
    def show_group(group, spec, result) -> None
    # One row per editable attribute (spec.editable_attrs, editor by type and
    # access), per `view` attribute (read-only text) and per `warn` attribute
    # (a warning line, only while its value is set). Rows grouped under their
    # `section` heading (first appearance order, rows without one first); a row
    # whose show_if is False in `result.visible` is hidden. A change applies at
    # once: binding.run(... set_values ...) = one undo step. A reset button on
    # an overridden value sets it to None. Errors from `result` shown under the
    # row, translated (i18n.tr_msg).

class AddDialog(QDialog):                   # ui/add_dialog.py
    def __init__(self, scene, groups, roots, parent=None)
    # "Add “Group 1” to:" and a list of the dynamic components (name, part
    # count, position) that add_problem accepts; chosen() -> root | None.

class AttributesEditor(QWidget):            # ui/attributes.py
    def __init__(self, app)
    def show_group(group, spec, inst, present=None) -> None
    # `present`: the part names this instance has groups for; other nodes are
    # not shown (deleted here).
    # Works on a copy of the definition. One fold section per node; each
    # attribute is a row (label, formula, evaluated value, error) that opens an
    # inline editor: label, type, default value, formula with an insert menu and
    # completion of references and functions (live check and preview), who may
    # see/edit it (incl. "warning"), section, show-if formula, min/max, options
    # as a table. A part's section starts with its geometry: "Stretched" or a
    # registered generator, and "Cuts into" (none or another part); its
    # generation problems (binding.problems) are listed there. "Add property" offers the reserved
    # attributes the node lacks and a custom attribute. Every finished edit (a
    # field left, a choice made, an attribute added, renamed or removed) is
    # applied at once: binding.run(... set_definition ...) = one undo step;
    # typing only updates the preview. A formula that does not parse holds the
    # copy back (dirty) until fixed; discard() drops it. A definition changed by
    # anything else (undo, redo) replaces the copy and reopens the editor with
    # fresh values; its own writes do not (focus stays where Tab put it).
    dirty: bool
```
## __init__.py

```python
def setup(app):
    # api_version check (2); add_panel(DynamicPanel);
    # add_context_menu: "Make Dynamic" on a component instance, "Component Options…" (shows the
    # panel, DynamicPanel.show_options) and "Bake Dynamic Component" on a
    # dynamic one; on groups that are no part: "Add as Part of “X”" when they
    # sit loose in dynamic root X, else "Add to Dynamic Component…" (a small
    # modal, ui/add_dialog.py, lists dynamic_roots) — then the root is selected
    # and the panel opens the new part; add_outliner_kind; on_document_changed -> panel.refresh() and
    # absorb_scale for dynamic instances whose xform carries a scale, only when
    # a command not seen before is on top of viewport.history.undo_stack (a
    # tool's live preview commits nothing; re-entrancy guarded). Without a new
    # command, a scaled instance gets preview_scale, and one whose scale went
    # away again (cancel, undo) gets relayout; any other one gets settle and
    # relayout (parts follow the definition; a matrix the host pushed down is
    # pulled back). Instances open for editing are left alone. A changed
    # placement bumps scene.version and asks the viewport to redraw.
```
