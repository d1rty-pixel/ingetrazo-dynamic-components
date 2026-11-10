# ingetrazo-dynamic-components

An [IngeTrazo](https://ingetrazo.com) extension that adds SketchUp-style dynamic
components: attributes and formulas that drive the size, position, visibility,
material and repetition of a component's parts.

Status: early development. Requires IngeTrazo 0.6.0 (Extension API 2).

## Install

`./install.sh` copies the package into IngeTrazo's plugins folder (on WSL it finds
the Windows one, `%APPDATA%\IngeTrazo\plugins`) and keeps the previous copy as
`.dynamic_components.bak`. IngeTrazo does not follow the repository, so run it
after every change and restart IngeTrazo. By hand:

Copy or symlink the `dynamic_components` package (the folder, not the repository)
into the IngeTrazo plugins folder, then restart IngeTrazo:

- Linux: `~/.local/share/ingetrazo/plugins/` (honours `$XDG_DATA_HOME`)
- Linux, Flatpak: `~/.var/app/com.ingetrazo.IngeTrazo/data/ingetrazo/plugins/`
- Windows: `%APPDATA%\ingetrazo\plugins\`

```
ln -s "$PWD/dynamic_components" ~/.local/share/ingetrazo/plugins/dynamic_components
```

**Extensions > Open plugins folder** in IngeTrazo creates and opens the folder.

## Use

Right-click a component instance: **Make Dynamic**. Everything else is in the
**Dynamic Components** tab of the side tray (closed by default, see Window >
Panels), for the selected instance:

- **Options**: the values users may change; each change is one undo step, ↺ goes
  back to the default. **Component Options…** in the context menu opens this.
- **Bake** freezes the instance as it is now into a plain component. Cutters and
  hidden parts are removed.
- One section per part: click an attribute to edit its label, type, formula
  (insert menu and completion for references and functions, checked live), who
  may see or edit it, limits and choices. A change is applied when you leave
  the field (Tab moves on), for every instance of the definition; one undo step
  each.

Scaling an instance with the Scale tool lays its parts out live while you drag
(boards keep their thickness) and stores the new size on release.

A group cannot be made *inside* a component (IngeTrazo keeps a component's parts
as they are). Make it outside, right-click it and choose **Add to Dynamic
Component…**: a small dialog lists the dynamic components that can take it, and
the group keeps its place in the model (one undo step). A group already sitting
in a dynamic component without being a part offers **Add as Part of “…”** in the
context menu and **Add as part** in the tab.

While a dynamic component is open for editing (double-click into it), the tab
shows it read-only; leave it to change options or attributes. A part deleted
inside it disappears from the tab, which offers **Remove from definition**.
Parts always follow the definition: a part moved by hand inside the component
goes back to where its attributes put it.

### Options layout

An attribute can name a **section** (options with the same section are shown
together under that heading) and a **Show if** formula (the option is shown only
while it is true, e.g. `=Plinth` or `=Shelf_Mode="fixed"`). The access **Shown as a
warning** makes a computed text appear as a warning while it is not empty.

### Generated parts and cutters (real holes)

Each part's section starts with **Geometry** and **Cuts into**:

- **Geometry: Board with holes, pockets and grooves** (`board@1`): the part is no longer
  stretched; its mesh is built at its size (`LenX/Y/Z`), so holes stay round and
  keep their spacing when the component grows. It can also take a
  **groove**: a box cutter that runs along the whole length of the board from one
  face (all grooves of a board the same way, and it must stay clear of the board's
  sides across it).
- **Cuts into: a part**: this part becomes a *cutter*. It is never drawn; its box
  is cut out of that part where they meet (a cylinder makes a round hole, a box a
  rectangular pocket or opening). Its position, `Copies` and `Hidden` (= cut off)
  come from formulas as usual. A cut must enter through one face (or go through
  two opposite ones) and stay inside it; it may also run the whole length of the
  board (a groove). Notches over a corner are not possible.

The holes are ordinary geometry, saved in the file and exported. Problems (a
cutter that reaches nothing, a cut over an edge) are listed in the part's section.
A generated part edited by hand is left alone: the tab says so and offers
**Regenerate** (the edits are lost). While you drag the Scale tool, generated
parts are stretched; they are rebuilt when you release. **Bake** keeps the holes
and removes the cutters.

### Ready-made models

Dynamic components are shared as `.igz` files: open one, or copy a component from
it into another document (it carries its definition). `models/` holds examples,
each in its own folder with a README. The extension contains nothing specific to
any one of them.

**System 32 cabinet** (`models/system32-cabinet/`): a carcass with sides, bottom,
top, back panel, a plinth that can be turned off, shelves and four rows of System 32 holes (Ø5 × 12 mm, every 32 mm from the
centred between bottom and top panel, front row 37 mm from the front edge, back row at a
multiple of 32 mm behind it; all values are options). In *From the height* mode
the number of shelves follows the height so that every gap stays between the
smallest and largest gap; shelves always sit on the hole raster. Wider than
1000 mm (an option) it gets a divider for every started 1000 mm, drilled through,
with the same shelves in every compartment. A warning appears when
the limits cannot both be kept.

### Language

The tab follows IngeTrazo's interface language. German, Spanish and French are
included; English is the source and the fallback (any other language, and any
string a catalog lacks, shows in English);
another language is one file, `dynamic_components/locale/<code>.json`
(`{"English text": "translation"}`). Labels you type into a definition are yours
and are not translated.

## Status and known limits

Implemented: SketchUp-style formulas (`=IF(…)`, `Parent!LenX`, `Part!Attr`),
attributes on the component and its direct parts, `X/Y/Z`, `RotX/Y/Z`,
`LenX/Y/Z`, `Hidden`, `Material`, `Copies`/`COPY`, options and attribute editor
in one side-tray tab, scaling an instance feeds `LenX/Y/Z` (live layout while
dragging), adding moved-in groups as parts, undo for every step, .igz round
trip, bake, option sections / show-if / warnings, `MOD`, generated boards with
real holes (`board@1`) and cutters, German,
Spanish and French.

Not yet, or unverified:

- A pasted or imported instance carries a copy of its definition and keeps
  working in another document. If that document already has a *different*
  definition under the same id, the document's own one wins.
- Scaling an instance and the move of that scale into `LenX/Y/Z` are two undo steps.
- Only one level of parts; nested dynamic components are not evaluated.
- Rotation order (`RotZ·RotY·RotX`) and `Copies` semantics (N extra copies) follow
  SketchUp from memory and are not verified against real files.
- No `.skp` import of SketchUp dynamic attributes yet (see `docs/DESIGN.md`).
- Interplay with Newton's "keep pose" is not handled yet.
- Translations: German, Spanish and French only (everything else in English).
- Generated boards: holes and pockets inside a face, and grooves along a whole board (no notches
  over an edge, no rotated cutters); construction holes and hinge cups are not in
  the cabinet template yet.

## Tests

`.venv` and `ingetrazo-source` are symlinks to a host IngeTrazo checkout (see
`CLAUDE.md`).

```
.venv/bin/python -m pytest tests -q
```
