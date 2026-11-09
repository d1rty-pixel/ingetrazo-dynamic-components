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

Right-click a component instance: **Make Dynamic**, then **Component Options...**
or **Bake Dynamic Component**. The **Dynamic Components** tab in the side tray
(closed by default, see Window > Panels) edits attributes and formulas.

## Status and known limits

Implemented: SketchUp-style formulas (`=IF(…)`, `Parent!LenX`, `Part!Attr`),
attributes on the component and its direct parts, `X/Y/Z`, `RotX/Y/Z`,
`LenX/Y/Z`, `Hidden`, `Material`, `Copies`/`COPY`, Component Options dialog,
attribute editor, scaling an instance feeds `LenX/Y/Z`, undo for every step,
.igz round trip, bake.

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
