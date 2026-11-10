# AGENTS.md

Guidance for coding agents and contributors working on Dynamic Components, an extension for the 3D modeller IngeTrazo that adds SketchUp-style dynamic components. All documentation is English ([README](README.md), [docs/manual.md](docs/manual.md), this file); only the UI has German, Spanish and French translations.

## Architecture

- `dynamic_components/` is the extension package that IngeTrazo loads (`setup(app)` in `__init__.py`). It targets IngeTrazo 0.6.0 / Extension API 2 and must not modify IngeTrazo core files.
- Design: [docs/DESIGN.md](docs/DESIGN.md). Module interfaces: [docs/contract.md](docs/contract.md) (binding; change it first when an interface changes).
- Layering is one-way: `formula`, `spec`, `evaluate`, `geometry` and `messages` import no Qt and no IngeTrazo module; `generators` and `binding` use the host model; `ui` uses PySide6 widgets; `__init__` wires them to the host.
- **Formulas come from documents we did not write:** fail closed, keep limits, never `eval`/`exec`/`compile`. A document may name a generator (`board@1`); it never carries code. A generator is versioned (`name@n`): a changed algorithm is a new version, never a change of an old one.
- Model data lives in `scene.plugin_data["dynamic_components"]` (definitions) and `group.ext["dynamic_components"]` (instances and parts) and is saved in the `.igz`. An instance carries a copy of its definition (`ext[...]["spec"]`) so that it survives a copy into another document.
- Nothing in the extension is specific to one component. Example components live in `models/`, each in its own folder with a README; a model may carry a build script, which uses only the public API.
- User-facing text goes through `tr()` (`N_()` for constants, `messages.Msg` in the pure modules); English is the source and the key. Catalogs are `dynamic_components/locale/<lang>.json`; `tests/test_i18n.py` checks that they are complete and have no unused entries.

## Development setup

The tests import IngeTrazo itself, so a checkout of the host must sit next to the extension as `ingetrazo-source/` (git-ignored; a symlink works):

```bash
git clone https://github.com/ingelibre/ingetrazo.git ingetrazo-source
```

Python 3.12 environment in `.venv` (git-ignored):

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
```

(Windows: `.\.venv\Scripts\python.exe`.) The tests ran against IngeTrazo 0.6.1.

## Tests

```bash
.venv/bin/python -m pytest tests -q
.venv/bin/python -m pytest tests/test_formula.py -q        # focused
```

Tests are hermetic: `QT_QPA_PLATFORM=offscreen`, no network, no user settings. `tests/test_cabinet.py` builds the System 32 cabinet from `models/system32-cabinet/build.py` and is the reference test for generated parts, cutters and dividers.

## Installing a development build

IngeTrazo runs what is in its plugin folder; it does not follow the checkout. `scripts/install-local.sh` copies the package there (on WSL it finds the Windows folder) and keeps the previous copy; restart IngeTrazo afterwards.

## Models

`models/system32-cabinet/system32-cabinet.igz` is written by its `build.py` (`python models/system32-cabinet/build.py [out.igz] [--lang de]`, with the host checkout and this repository on `PYTHONPATH`). Rebuild it whenever the formulas in `build.py` or the extension's data format change, and commit the result.

## Releasing

1. Update `__version__` in `dynamic_components/__init__.py`, `CHANGELOG.md` and the badges if the IngeTrazo version changed.
2. Run the tests; rebuild the model if needed.
3. `python scripts/package.py` builds `dist/dynamic_components-<version>.zip` (one folder, reproducible hash).
4. Tag `v<version>`, create the GitHub release and attach the zip.
5. Catalog: a pull request to [ingetrazo-extensions](https://github.com/d1rty-pixel/ingetrazo-extensions) with `extensions/dynamic_components.toml` (template: `scripts/catalog-entry.toml`; `download` is the release asset, `sha256` is the hash of that exact zip).
