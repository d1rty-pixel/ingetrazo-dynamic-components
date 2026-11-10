# Dynamic components for IngeTrazo — design sketch

Status: phases 0–4 implemented (2026-11-09). Sections 13–16 (generators and
cutters, option layout, the System 32 cabinet, translations) were added the same day
and are phase 6.

**Decisions taken 2026-11-09:**
1. Formulas live in a document registry keyed by definition id; instances keep only
   the definition id and their overrides (section 3).
2. Existing SketchUp dynamic components must keep working, so the formula surface is
   SketchUp-compatible and `.skp` import of their attributes is in scope (sections 5, 8).
3. This is its own repository and an **extension only**: no change to the IngeTrazo
   core, no host proposals. Anything the extension API cannot do is out of scope or
   must be solved inside the extension (sections 6, 9).

Still open: the keep-pose rule with Newton (section 6). Facts about
the current code are marked with the file they come from; everything marked
**(to verify)** was not read yet and must be checked before implementation starts.

## 1. Goal and non-goals

**Goal.** A component whose size, position, visibility, material and repetition
follow *attributes*, and whose attributes can be formulas over other attributes.
Typical cases: a door whose frame follows the opening width, a shelf with N boards,
a fence of any length, a stair with the step count derived from the rise.

**Non-goals.**
- Animation and click-to-interact (SketchUp's Interact tool). That is Newton's job.
  A discrete choice ("door type B") is only a parameter change and goes through the
  options dialog.
- Replacing Windowizer or other extensions that generate geometry in Python. They
  keep working; see tier 2 in section 4.
- A general scripting language. Formulas are expressions, not programs.

## 2. What the code already gives us

| Fact | Where |
|---|---|
| An instance shares a prototype `mesh` with its siblings; `xform` maps local to world. | `core/group.py` (`Group.xform`, `Group.mesh`) |
| A container owns nested placements in `children`, each over a shared prototype. | `core/group.py` |
| Scale lives in the columns of `xform` (instances) or in `axes` (classic groups); `group_scale()` reads it. | `core/group_scale.py` |
| `Group.ext[key]` is a per-container slot: deep-copied with copies, saved in the .igz, separate from `ifc`. | `core/group.py`, `core/history.py:3849`, `formats/igz.py:675,1299` |
| A document-level registry keyed by container uid is an established pattern. | `examples/extensions/windowizer.py:758` (`scene.plugin_data`) |
| "Keep in File" stores placement-free template instances that share prototype and subgroups with live copies. | `core/kept_components.py` |
| Geometry edits first `materialize` an instance (make unique). | `core/group.py` |

Consequence that shapes the whole design: **the definition is not an object**. It is
only "the prototype mesh several instances happen to share". Anything that must be
true for *all* instances of a definition (the formulas) has no natural home yet.

## 3. Data model

Two layers, mirroring SketchUp's split:

- **Spec (definition level):** the list of attributes with name, label, type, unit,
  default, formula, editability, choice list, and for each part which attributes
  drive its transform. Identical for all instances.
- **State (instance level):** only the values the user *overrode* (e.g. `LenX = 0.9`).
  Everything else is computed from the spec.

Instance record, in `group.ext["dynamic"]`:

```json
{"def": "d3f1…", "set": {"width": 0.9, "doortype": "B"}}
```

Spec, in a document-level registry keyed by definition id (same pattern as
Windowizer's `registry(scene)`):

```json
{
  "d3f1…": {
    "name": "Door",
    "attrs": {
      "width":  {"label": "Width", "type": "length", "default": 0.9, "edit": "box", "min": 0.6, "max": 1.2},
      "leaf_w": {"formula": "width - 2 * frame"},
      "frame":  {"type": "length", "default": 0.05, "edit": "none"}
    },
    "parts": {
      "Leaf":  {"lenx": "leaf_w", "x": "frame", "hidden": "doortype = 'none'"},
      "Frame": {"copies": "2", "x": "COPY * (width - frame)"}
    }
  }
}
```

**Why a registry and not the spec inside every instance (rejected alternative):**
copies of the spec drift apart, and "edit the definition" would have to find and
patch every sibling. The registry makes a definition edit one write. The price is
that the registry must travel: `import_igz`, copy/paste between documents and "Keep
in File" templates have to carry the spec along and merge by content hash on
conflict. This is the main integration cost of the design.

## 4. How attributes reach the geometry

### Tier 1 — transform binding (core, data only)

A part's evaluated attributes are written to *placement properties*, never to the
mesh:

- `LenX/LenY/LenZ` → scale of the part's `xform`, relative to its rest size
  (the bounding box when the definition was authored)
- `X/Y/Z`, `RotX/RotY/RotZ` → translation / rotation in the parent's frame
- `Hidden`, `Material` → existing `hidden` / `material` fields
- `Copies` → the part is expanded into N child placements, each with `COPY` (the
  index) available in its formulas

Why this is the right first tier: **prototype meshes stay shared.** A thousand doors
with a thousand widths still share one mesh; only `xform`s differ, so no
`materialize`, no memory blow-up, and it fits the light-components direction in
`ROADMAP.md`. It is also exactly what SketchUp does, so authoring knowledge carries
over.

Known limit: stretching distorts things that must not stretch (frame thickness,
a stair's tread depth). The standard answer is to model such things as several parts,
each stretched only along its own length. Copies handles repetition.

### Tier 2 — generators (extension code)

For geometry that scaling cannot express (holes that must stay round, pane grids,
arbitrary outlines) a part names a *generator* that builds its mesh at its final
size from the attributes. Section 13 has the design; Windowizer is not migrated.

## 5. Formula language

- Expressions only, parsed with Python's `ast` against a **whitelist**: arithmetic,
  comparison, `and/or/not`, names, a fixed function set (`if`, `min`, `max`, `abs`,
  `round`, `floor`, `ceil`, `sqrt`, `sin`, `cos`, `choose`, `lookup`). No attribute
  access, no subscripts, no calls outside the whitelist, no comprehension.
- Reserved names: `LenX/Y/Z`, `X/Y/Z`, `RotX/Y/Z`, `Material`, `Hidden`, `Copies`,
  `COPY`, `Parent.<attr>`, `<PartName>.<attr>`.
- Lengths are metres internally; unit handling happens at the UI edge.
- Dependency graph between attributes, topological order, cycle detection.
- **Fail closed:** a formula that errors, cycles, or exceeds limits leaves the last
  good values in place and is flagged in the panel. Never crash a redraw and never
  guess a value.
- **Limits** (formulas arrive inside .igz files we did not write): max expression
  length, AST depth, `Copies` cap (e.g. 1000), evaluation step budget.

Surface syntax is **SketchUp-compatible** (decision 2): leading `=`, `IF(a>1,b,c)`,
`Parent!LenX`, case-insensitive names, `CHOOSE`, `OPTIONINDEX`, `LOOKUP`, `ROUND` and
the rest of the function set that real `.skp` dynamic components use **(function list
and exact semantics from memory; collect from sample files and SketchUp's DC
documentation before phase 0 is final)**. The functions collected so far from
SketchUp's own dialog, with their status here, are in
[sketchup-functions.md](sketchup-functions.md). Compatibility is the largest part of the
evaluator's scope: the whitelist above is the *safety* rule, the SketchUp function
set is the *feature* rule, and the parser must reject everything outside both.

## 6. When evaluation runs

1. The user changes a value in the **options dialog** → one undo step.
2. The user scales the instance with the **Scale tool** → intercepted, see below.
3. The spec is edited → all instances of that definition re-evaluate.
4. Open / import → evaluate lazily, only instances whose stored result is stale
   **(to verify: whether to persist evaluated transforms or recompute on load)**.

Only instances with `ext["dynamic"]` pay anything; everything else is untouched.

**Scale tool.** After a scale commit on a dynamic instance, decompose the applied
scale into `LenX/Y/Z` overrides, reset the `xform` scale to 1, then evaluate. A spec
flag per axis says which scale handles are allowed (none = locked). **No core hook is allowed (decision 3).** The extension can only react afterwards,
through `app.on_document_changed`: notice that a dynamic instance's `xform` now carries
a scale, convert it to `LenX/Y/Z` overrides and normalise `xform`. Whether that can be
one undo step together with the user's scale, or becomes a second step, depends on the
extension API **(to verify; if it is a second step, say so in the manual rather than
patching the core)**.

**Newton** (`../ingetrazo-newton`, read 2026-11-09). Newton is an extension in its own
repo. It keeps its settings in `group.ext[KEY]`, a different key from `"dynamic"`, so
the two do not collide, and `copy_group` / `nested_clone` deep-copy `ext`, so the
dynamic record survives a simulation. A simulation runs in a temporary workspace on
clones that share the source meshes (`newton/model.py`, `nested_clone`); the model
itself is untouched until Reset. Consequences:

- Evaluate before the simulation starts; Newton snapshots the evaluated `xform`s.
  While it runs, the engine must not re-evaluate the model.
- Scale in an `xform` stays in the body's mesh offset (`offsets[uid] = translate(-origin)
  · xform`), so a stretched part simulates as a rigid body of its stretched size.
- **Conflict to resolve:** "keep pose" on Reset writes the simulated `xform` back into
  the model (`newton/keep_pose.py`). If that part's `X/Y/Z` is formula-driven, the next
  evaluation overwrites the kept pose. Rule proposed: the engine owns the *rest pose*
  of a part; a kept Newton pose on a formula-driven axis is dropped (or Newton warns)
  at the next evaluation. The top-level instance's world placement is never owned by
  the engine, only the placement of parts inside it.

## 7. UI

- **Component Options** dialog (use): one row per attribute with `edit != none`;
  text box, list or checkbox by type; Apply = one undo step.
- **Component Attributes** panel (authoring): table of attributes and per-part
  bindings with formula cells, errors shown inline. Later.
- The spec is plain JSON, so it is Git-friendly and writable by hand or through the
  AI bridge (`docs/ai-bridge.md`).

## 8. Persistence and interchange

- .igz: `ext["dynamic"]` already round-trips; the registry goes through
  `set_document_data` / `plugin_data` **(to verify: that core, not only extensions,
  may own a registry key, or whether it needs its own scene field)**.
- Export (SKP, DAE, glTF, IFC): write the evaluated geometry, as for any component.
- Import of SketchUp DCs (wanted: old `.skp` dynamic components must keep working).
  They sit in the `dynamic_attributes` attribute dictionary of the definition (keys
  like `_lenx_formula`; **from memory — verify against a real file**). IngeTrazo's
  own `.skp` import reads no attribute dictionaries at all (grep of the repo finds
  nothing) and may not be touched, so the extension has to read the `.skp` itself via
  OpenSKP (an optional dependency of the host, `docs/skp-backend.md`) **(to verify:
  whether OpenSKP exposes attribute dictionaries at all — this decides whether phase 5
  is possible)** and then match the dictionaries to the components the host imported,
  e.g. by definition name and path **(to verify: what the host keeps on an imported
  instance that makes the match reliable)**. Highest-risk item of the design.

  *OpenSKP docs checked 2026-11-09 (README, `docs/API_DESIGN.md`, `docs/DEVELOPER_GUIDE.md`;
  `BINARY_FORMAT.md` and `LANGUAGE_PARITY.md` not read):* the README lists "Dynamic
  Components" as supported and says it "extracts dynamic component attribute key-value
  pairs" for 2013–2020 and 2021+ files, and `buildScene`'s `meshIndex` carries "dynamic
  properties" per baked mesh. Full attribute-dictionary support (9 value types) is
  listed for the Python reader only. The docs name **no** accessor for reading
  attributes and no field linking an instance to its definition, so whether the
  formulas (not only the values) come out, and with which keys, is not answerable from
  the docs. It needs the code or a real DC `.skp`; there is none available at the
  moment, so phase 5 stays unverified and last.

## 9. Phases

| # | Unit | Result |
|---|---|---|
| 0 | Spec schema, safe evaluator, dependency graph, limits — pure Python, no Qt | Unit tests only; no behaviour change |
| 1 | Registry + instance state, evaluate → `xform` / `hidden` / `material`, options dialog, undo | A hand-written spec works end to end |
| 2 | `Copies` / `COPY` | Fence, shelf, stair |
| 3 | React to a scale on a dynamic instance (extension API only) | Scaling edits `LenX` after the fact |
| 4 | Authoring panel | No hand-written JSON needed |
| 5 | Import SketchUp DC attributes (needs OpenSKP to expose them) | Old `.skp` dynamic components work |
| 6 | Generators and cutters (`board@1`), option sections, `show_if`, warnings, cabinet template, translations (sections 13–16) | Real System 32 holes; a cabinet that lays out its own shelves |

Each phase is shippable alone; phase 0 touches no existing file.

## 10. Decisions

Taken (2026-11-09): registry with definition ids; SketchUp-compatible formulas with
`.skp` import in scope; own repo, extension only, never the core.

Open:
1. **Keep pose with Newton** (section 6): the engine owns the rest pose of parts, a
   kept Newton pose on a formula-driven axis is dropped or Newton warns. Needs the
   Newton owner's agreement.
2. **Feasibility of `.skp` DC import** (sections 8, 9): depends on OpenSKP and on how
   an imported instance can be matched to its dictionary. Phase 5 may shrink to
   "convert a DC by hand" if it fails.

## 11. Risks

- **Untrusted formulas** in opened .igz files: mitigated by whitelist, limits and
  fail-closed evaluation; needs a dedicated test set (hostile inputs).
- **Registry travel** (import, paste across documents, kept templates) is easy to get
  subtly wrong and is the likeliest source of bugs.
- **Undo granularity:** one dialog Apply or one scale drag must be exactly one step,
  including all re-evaluated children.
- **Explode view** (`core/explode.py`) already offsets parts in the container's frame;
  it must compose with `X/Y/Z` rather than overwrite it **(to verify)**.
- **`Copies` cost** on big models: cap and measure against the benchmark models
  before raising the cap.

## 12. Rollout, rollback, tests

- **Rollout:** behind the instance's `ext["dynamic"]` presence; documents without it
  load and save byte-for-byte as before. Release note per phase.
- **Rollback:** a dynamic instance can be *baked* (drop the `ext` record, keep the
  evaluated placements) — also the safe fallback when a spec fails to load. An older
  IngeTrazo ignores the unknown `ext` key and shows the last evaluated geometry.
- **Tests:** evaluator (valid, cyclic, hostile, over-limit); registry merge on import;
  undo/redo round trip; scale decomposition per axis and locked axes; copies of an
  instance keep `def` and overrides; .igz round trip; a benchmark with N instances
  to show prototype sharing is preserved.

## 13. Generators and cutters (tier 2)

**Problem.** Tier 1 stretches a part's shared mesh. That is right for a plain board,
wrong for a board with holes: a System 32 hole row would turn into ovals and its
32 mm pitch would stretch with the height. Holes must be real geometry (they are
exported, sectioned and machined), so they cannot be markers either.

**Idea.** A part may name a *generator*. Instead of stretching it, the binding asks
the generator for a mesh at the part's final size and only places it (rotation and
translation, no scale). Other parts can be *cutters* of a generated part: their
evaluated boxes are cut out of it. Positions still come from formulas and `Copies`,
so everything the formula engine can express (raster, adjustable ranges, toggles)
works for holes without any new syntax.

```json
"seite_links":  {"gen": "board@1", "attrs": {"lenx": …, "leny": …, "lenz": …}},
"bohr_lv":      {"cut": "seite_links", "attrs": {"copies": …, "x": …, "z": …}}
```

### Rules

- **Code, not data.** A generator is Python inside an installed extension. A
  document only names it (`"board@1"`) and supplies values. Python stored in a
  document is never run (formulas come from documents we did not write).
- **Versioned names.** `board@1` never changes its output for the same input. A
  changed algorithm is `board@2`; documents keep what they asked for.
- **Deterministic and cached.** The mesh is a function of (generator, size, cuts,
  paint). The SHA-1 of that is the *key*. A part whose key did not change keeps its
  mesh; equal keys share one mesh object across parts and instances (a session
  cache), so 50 equal cabinets hold two side meshes, not 100.
- **Stored in the document.** The generated mesh is the part's ordinary mesh and is
  saved in the .igz. IngeTrazo without this extension, every exporter and an older
  version show the real holes. Opening a document regenerates nothing while keys
  match.
- **Fail closed.** An unknown generator, a generator that raises or exceeds its
  limits, or a cutter it cannot handle leaves the last mesh in place and reports the
  problem on the part. A bad cutter is reported and skipped; the others still cut.
- **Hand edits win until the user decides.** The record on the part keeps a
  fingerprint (face and vertex count) of what was generated. If the mesh no longer
  matches (someone pushed/pulled inside the board), the binding does not overwrite
  it: the part shows "edited by hand" and the panel offers *Regenerate* (discard the
  edits). *Bake* keeps the edited geometry for good.
- **Live preview stretches.** While the Scale tool drags, generated parts are not
  rebuilt (≈0.1 s per board is too slow per frame); they are scaled from the size
  they were built for. Release rebuilds them. Every other part keeps its real live
  layout.
- **Cutters are tools.** A cutter part is never drawn (`hidden` is forced on); its
  own `Hidden` attribute means *inactive* (no cut). *Bake* removes cutter parts.
  A cutter cuts every placement (and copy) of its target that it meets.

### `board@1`

A box of size `LenX × LenY × LenZ`, with these cuts, built directly (no boolean
library: the host's manifold3d is optional and absent in the test environment):

A cutter cuts with its local bounding box, taken into the board's frame. Its mesh
says the shape: a plain box (at most 6 faces) cuts a rectangle, anything else (the
template's cylinders) a circle; a "round" box whose two sides across the cut differ
is refused.

| Cut | Recognised when the cutter box (in the board's frame) … | Result |
|---|---|---|
| Round hole | reaches the board's faces along exactly one axis, from one side (blind) or both (through) | Cylinder of that diameter (12 segments up to Ø10, 24 up to Ø40, 32 above), soft seams |
| Rectangular pocket / cut-out | as above, cutter is a box | Rectangular pocket (blind) or opening (through) |

Placements pass through float32 matrices (≈2·10⁻⁷ m at 2 m), so "touching" and
"equal" mean within 1 µm.

A cut must stay inside its face (its footprint may not touch the face's edges; grooves
are the exception, below), must be axis-aligned with the board (rotations by multiples of 90° are
fine) and may not touch or overlap another cut. Anything else is reported and
skipped. Limits: 2000 cuts and 200 000 faces per board.

The board keeps its paint: on the first generation the largest face's `color`/`mat`
attributes are recorded and given to every generated face; the group's own paint
works as before.

Measured (2026-11-09, WSL2, Python): a 2000 × 560 × 19 mm side with 120 blind holes
Ø5 × 12 builds in ≈65 ms and triangulates in ≈190 ms (the triangulation happens in
the renderer anyway).

### Registry for other extensions

`generators.register(name, build)` adds a generator (`name` = `"kind@version"`).
`build(size, origin, cuts, params) -> geometry.Shape` gets the size, the box origin
in part coordinates, the cutter boxes and the part's evaluated attributes, and
returns plain polygons; the binding turns them into a mesh. Shapes are pure data so
a generator can be unit-tested without Qt.


### Grooves in `board@1`

A rectangular cutter that runs along the **whole length**
of the board from one face is a **groove**. The board is then the extrusion of its
profile with slots, built directly like `board@1` (entry face in strips, notched
end faces, two walls and a floor per groove). Rules: all grooves of a board run the
same way from the same face; a groove may not reach the board's sides across it
(that would be a rebate: reported); it is always rectangular; holes and pockets in
the groove's face must stay in a strip, clear of the groove. A groove is a normal
cut for the rest (its position and `Hidden` come from formulas). Notches over a
corner are still not possible.

## 14. Option layout: sections, conditional rows, warnings

A cabinet has 20 options; one flat list does not work. Three attribute fields:

- `section` (text): rows with the same section are shown together under a heading,
  sections in the order they first appear; rows without one come first.
- `show_if` (formula): the row is only shown while it evaluates to true
  (`=Sockel`, `=FB_Modus="fix"`). An error shows the row (fail open: never hide an
  option because a formula broke) and reports the error. It only affects the
  Options form, never evaluation.
- access `warn`: a computed attribute (usually text) shown as a warning row while
  its value is not empty/false. This is how a template reports "these limits cannot
  both be met" without a new concept in the engine.

`MOD(number, divisor)` (Excel semantics, sign of the divisor) joins the functions;
it makes a 2D grid from one `Copy` index.

## 15. Worked example: cabinet with plinth, shelf automatic and System 32

The model `models/system32-cabinet/` holds this component (`.igz`, and the script
that builds it). The extension contains nothing specific to it. It uses only the
features above; it is also the reference test for them. Root frame: X width, Y depth (front at 0), Z height.

**Parts.** Two sides (`board@1`), bottom, top, back panel, plinth panel, shelves
(`Copies`), four hole rows (cutters: left/right × front/back).

**Plinth.** Sides run to the floor; with the plinth on, the bottom sits at
`Z_Boden = IF(Sockel, Sockel_H, 0)` and a plinth panel, set back by
`Sockel_Rueck`, closes the gap (`Hidden = NOT(Parent!Sockel)`).

**System 32.** The row runs every 32 mm between the bottom and the top panel and is
centred there: `Loch_K = FLOOR((Innen_H − 2·Rand_Min)/Raster, 1) + 1` holes, the
first at `Z_Erst = Innen_Unten + (Innen_H − (Loch_K − 1)·Raster)/2`. The first and
the last hole are therefore the same distance from the panels (Hettich's advice, so
the sides can be swapped left/right); `Rand_Min` (32 mm) is the smallest distance,
the distance is at most one raster step larger. Source: Hettich, Ratgeber
Möbeltechnik (Ø5, 32 mm, 37 mm from the front edge; equal first/last distance); the
exact distance to the panels is not fixed by the standard and is an option. Front
row at `Reihe_V` (37 mm), back row at a multiple of 32 mm
behind it (`Reihe_H`), so mounting plates and runners fit. Diameter and depth are
options (Ø5 × 12 mm by default; the values differ between hardware makers, so none
is hard-coded). The cutter boxes stick out of the inner face by 1 mm so they clearly
cross it.

**Shelves.** With n shelves the gap is `(H − n·t)/(n+1)`; keeping it within
`[Fach_Min, Fach_Max]` gives `n ≥ (H − max)/(max + t)` and `n ≤ (H − min)/(min + t)`.
Automatic mode takes the smallest n. Shelves always sit on the hole raster
(`ROUND((ideal − Traeger − Z_Erst)/Raster)`), which moves a gap by up to ±16 mm; a
formula cannot take a minimum over copies, so n is chosen with limits narrowed by
half a raster and the snapped gaps stay within the user's limits. A `warn`
attribute reports when no n fits (or, in fixed mode, when the gap is outside the
limits). `Traeger` is the shelf-support offset from hole centre to shelf underside.

**Back panel groove.** The back panel sits in a groove in both sides, the bottom and
the top (`board@1`, four cutters): `Rueck_Abstand` (10 mm) from the rear edge,
`Nut_T` (8 mm) deep, `Rueck_Dicke + 1 mm` wide, so the panel has 0.5 mm play at the
sides. The panel goes `Nut_T − 1 mm` into each groove. Bottom and top run to the
rear edge; shelves, dividers and the back hole row stop in front of the groove
(`Rueck_Y`). Without a back panel the cutters are off.

Not in this template yet: construction holes for connectors (Ø8/Ø15), hinge cups
(Ø35 on doors).

## 16. Translations

The extension follows the host's interface language (`core.i18n.current_language`).
English is the source and the key, like the host: `locale/<lang>.json` holds flat
`{english: translation}` maps; a missing entry falls back to English.

- Every user-facing string goes through `tr()`; constants that are translated later
  are marked `N_("…")`.
- Messages from the pure modules (`formula`, `spec`, `evaluate`) cannot import the
  host, so they are `messages.Msg` objects: a `str` holding the English text that
  also carries its template and parameters. The UI translates them with
  `tr_msg()`; nested messages ("Copy 3: Division by zero") translate part by part.
- What the user typed (labels, option names, part names in a document) is content
  and is never translated. The cabinet template writes its labels in the language
  active when it is inserted.
- A test checks that every catalog has an entry for every `tr`/`N_`/`Msg` string in
  the code, with the same `{placeholders}`.

Shipped: German, Spanish, French; `en.json` is the host-style empty identity map
(English is the source, so it needs no entries). Fallback order: the exact tag
(`fr-CA`), its base language (`fr`), English. Another language is one JSON file.
