# ingetrazo-dynamic-components

An [IngeTrazo](https://ingetrazo.com) extension that adds SketchUp-style dynamic
components: attributes and formulas that drive the size, position, visibility,
material and repetition of a component's parts.

Status: early development. Requires IngeTrazo 0.6.0 (Extension API 2).

## Install

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
- **Bake** freezes the instance as it is now into a plain component.
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

## Status and known limits

Implemented: SketchUp-style formulas (`=IF(…)`, `Parent!LenX`, `Part!Attr`),
attributes on the component and its direct parts, `X/Y/Z`, `RotX/Y/Z`,
`LenX/Y/Z`, `Hidden`, `Material`, `Copies`/`COPY`, options and attribute editor
in one side-tray tab, scaling an instance feeds `LenX/Y/Z` (live layout while
dragging), adding moved-in groups as parts, undo for every step, .igz round
trip, bake.

Not yet, or unverified:

- A dynamic instance pasted or imported into **another** document arrives without
  its definition and behaves as a plain component.
- Scaling an instance and the move of that scale into `LenX/Y/Z` are two undo steps.
- Only one level of parts; nested dynamic components are not evaluated.
- Rotation order (`RotZ·RotY·RotX`) and `Copies` semantics (N extra copies) follow
  SketchUp from memory and are not verified against real files.
- No `.skp` import of SketchUp dynamic attributes yet (see `docs/DESIGN.md`).
- Interplay with Newton's "keep pose" is not handled yet.
- User-facing text is English only.

## Tests

`.venv` and `ingetrazo-source` are symlinks to a host IngeTrazo checkout (see
`CLAUDE.md`).

```
.venv/bin/python -m pytest tests -q
```
