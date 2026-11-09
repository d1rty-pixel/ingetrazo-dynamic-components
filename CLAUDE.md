# ingetrazo-dynamic-components

An IngeTrazo extension (Extension API 2, IngeTrazo 0.6.0) that adds SketchUp-style
dynamic components: attributes and formulas that drive the size, position,
visibility, material and repetition of a component's parts.

- Design: `docs/DESIGN.md`. Module interfaces: `docs/contract.md` (binding; change
  it first when an interface changes).
- **Extension only.** Never modify the IngeTrazo source (`ingetrazo-source/` is a
  symlink to the host checkout, read it for reference only).
- Layering is one-way: `formula`, `spec`, `evaluate` import no Qt and no IngeTrazo
  module; `binding` uses the host model; `ui` uses PySide6 widgets.
- Formulas come from documents we did not write: fail closed, keep limits, never
  `eval`/`exec`/`compile`.

## Development

Environment: `.venv` and `ingetrazo-source` are git-ignored symlinks to the host
checkout (`../ingetrazo/.venv`, `../ingetrazo`).

```
.venv/bin/python -m pytest tests -q
.venv/bin/python -m pytest tests/test_formula.py -q        # focused
```

Tests are hermetic: `QT_QPA_PLATFORM=offscreen`, no network, no user settings.
