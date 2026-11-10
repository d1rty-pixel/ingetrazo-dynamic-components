# Dynamic Components for IngeTrazo

[![Licence](https://img.shields.io/github/license/d1rty-pixel/ingetrazo-dynamic-components)](LICENSE)
![IngeTrazo](https://img.shields.io/badge/IngeTrazo-0.6.0%2B-blue)
![Extension API](https://img.shields.io/badge/Extension%20API-2-blue)
![Python](https://img.shields.io/badge/Python-3.12-informational)
[![Windows: tested](https://img.shields.io/badge/Windows-tested-success)](#platform-status)
[![Linux: test suite only](https://img.shields.io/badge/Linux-test%20suite%20only-yellow)](#platform-status)
[![macOS: not tested](https://img.shields.io/badge/macOS-not%20tested-lightgrey)](#platform-status)

Dynamic Components is an extension for the 3D modeller [IngeTrazo](https://github.com/ingelibre/ingetrazo). It picks up the idea of SketchUp's dynamic components: a component gets attributes and formulas that drive the size, position, rotation, visibility, material and repetition of its parts, so a cabinet that you stretch lays out its own shelves, a fence adds its own posts, and the options appear in a panel instead of in the model.

## What it can do

- **Attributes and formulas:** SketchUp-style formulas (`=IF(Width > 1, 2, 1)`, `Parent!LenX`, `Part!Attr`, `COPY`) on a component and its parts, in a small interpreter of its own (no `eval`).
- **Options:** the values users may change, in sections, with *show if* conditions and warnings; every change is one undo step.
- **Repetition:** `Copies` makes a part repeat; a grid of copies from one index (`MOD`).
- **Scaling:** scaling an instance with the Scale tool feeds its size attributes; parts keep their thickness while you drag.
- **Real holes and grooves:** generated boards with round holes, pockets and grooves, cut by *cutter* parts, so holes stay round and keep their spacing when the component grows.
- **Sharing:** the definition is saved in the `.igz` and travels with a component when you copy it into another document.
- **Bake:** freezes an instance into plain geometry.
- **Languages:** the panel follows IngeTrazo's language: English, German, Spanish, French.

Not yet included: nested dynamic components, importing SketchUp's dynamic attributes from `.skp`, notches over a corner. All limits are listed in the [manual](docs/manual.md#limits) and in [known issues](docs/known-issues.md).

## Quick start

1. Install the extension, see [Installation](#installation) below, and restart IngeTrazo.
2. Open [`models/system32-cabinet/system32-cabinet.igz`](models/system32-cabinet/README.md) and select the cabinet.
3. Open the **Dynamic Components** tab of the side tray (Window → Panels, closed by default) and change the width, the height or the shelves. Or scale the cabinet with the Scale tool.
4. To make your own: right-click a component instance → **Make Dynamic**, then see the [manual](docs/manual.md).

## Installation

The extension needs IngeTrazo 0.6.0 or later. It needs nothing else: no runtime, no extra packages.

**From the extension library.** In IngeTrazo open **Extensions → Manage extensions…**, search for **Dynamic Components** on the **Browse** tab, press **Download** and restart IngeTrazo. *Dynamic Components is not listed in the library yet; until it is, install it by hand.*

**By hand.** Download `dynamic_components-<version>.zip` from the [releases](https://github.com/d1rty-pixel/ingetrazo-dynamic-components/releases) and unpack it into IngeTrazo's plugin folder, so that `…/plugins/dynamic_components/__init__.py` exists, then restart IngeTrazo:

| Installation | Plugin folder |
|---|---|
| Windows | `%APPDATA%\IngeTrazo\plugins\` |
| Linux | `~/.local/share/ingetrazo/plugins/` |
| Linux, Flatpak | `~/.var/app/com.ingetrazo.IngeTrazo/data/ingetrazo/plugins/` |

**Extensions → Open plugins folder** in IngeTrazo creates and opens it. From a checkout, `scripts/install-local.sh` copies the package there. Updating, uninstalling and checking that it works: [docs/installation.md](docs/installation.md).

## Platform status

| Platform | Status |
|---|---|
| Windows (IngeTrazo installer) | tested by hand; test suite |
| Linux | test suite (offscreen, no GUI run by hand) |
| macOS | not tested |

## Example models

| Model | What it shows |
|---|---|
| [`models/system32-cabinet/`](models/system32-cabinet/README.md) | A cabinet with plinth, automatic shelves, dividers above 1000 mm, a back panel in a groove and System 32 hole rows. Made of what the interface offers; nothing in the extension is specific to it. |

## Documentation

| Document | Content |
|---|---|
| [docs/installation.md](docs/installation.md) | Installing the extension: extension library, manual per platform, release zip, update, verification |
| [docs/manual.md](docs/manual.md) | How to use every function: attributes, formulas, options, generated parts, sharing, limits |
| [docs/faq.md](docs/faq.md) | Frequently asked questions |
| [docs/known-issues.md](docs/known-issues.md) | Known limits and open points |
| [docs/sketchup-functions.md](docs/sketchup-functions.md) | SketchUp's formula functions against ours |
| [docs/DESIGN.md](docs/DESIGN.md) | Design: how it works and why |
| [docs/contract.md](docs/contract.md) | Module interfaces (binding for development) |
| [models/system32-cabinet/README.md](models/system32-cabinet/README.md) | The example model |
| [scripts/README.md](scripts/README.md) | Helper scripts: install, package |
| [CHANGELOG.md](CHANGELOG.md) | What changed, per release |
| [AGENTS.md](AGENTS.md) | Development setup, tests and conventions |

## Licence

GNU General Public License v3.0 or later, like IngeTrazo. See [LICENSE](LICENSE).
