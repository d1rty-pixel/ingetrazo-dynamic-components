# Changelog

Notable changes to Dynamic Components, the dynamic component extension for IngeTrazo. Versions follow the [GitHub releases](https://github.com/d1rty-pixel/ingetrazo-dynamic-components/releases); the version number lives in `dynamic_components/__init__.py` (`__version__`). Changes not yet released are listed under "Unreleased".

## Unreleased

## 0.1.0 — 2026-11-10

First public version.

### Added

- **Dynamic components**: *Make Dynamic* on a component instance; attributes and formulas on the component and its direct parts drive `X/Y/Z`, `RotX/Y/Z`, `LenX/Y/Z`, `Hidden`, `Material` and `Copies`.
- **Formula language** in an interpreter of its own (no `eval`): SketchUp-style syntax (`=IF(…)`, `Parent!LenX`, `Part!Attr`, `COPY`), `MOD`, text and trigonometry functions, with limits on size, depth, steps and copies. A failing formula keeps its last good value.
- **Side-tray tab** *Dynamic Components*: options for the user, an attribute editor with live formula checking, **Bake**; sections, *show if* conditions and warnings; every change is one undo step.
- **Scaling** an instance feeds `LenX/Y/Z`; live layout while dragging, boards keep their thickness.
- **Adding groups** to a dynamic component from the context menu, and removing parts from the definition.
- **Generated parts**: the generator `board@1` builds a board at its size with real round holes, pockets and grooves, cut by **cutter** parts (*Cuts into*). Holes stay round and keep their spacing when the component grows; the mesh is saved in the `.igz`. A part edited by hand is left alone (*Regenerate*).
- **Sharing**: a component carries a copy of its definition, so it keeps working when copied into another document.
- **Bake** removes cutters and hidden parts and keeps the generated geometry.
- **Translations**: German, Spanish and French.
- **Example model** `models/system32-cabinet/`: a cabinet with plinth, automatic shelves on the System 32 raster, dividers for every started 1000 mm, a back panel in a groove and System 32 hole rows; with its build script.
- `scripts/install-local.sh` and `scripts/package.py` (release zip with a reproducible hash).

### Documentation

- [Manual](docs/manual.md), [installation](docs/installation.md), [FAQ](docs/faq.md), [known issues](docs/known-issues.md), [design](docs/DESIGN.md), [module contract](docs/contract.md) and [SketchUp's functions against ours](docs/sketchup-functions.md).
