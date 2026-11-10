# Installing Dynamic Components

The extension needs IngeTrazo 0.6.0 or later (Extension API 2). It needs nothing else: no runtime, no extra Python packages.

## Status per platform

| Platform | Status |
|---|---|
| Windows (IngeTrazo installer) | tested by hand; test suite |
| Linux | test suite (offscreen, no GUI run by hand); plugin folder per the table below |
| macOS | not tested |

## A. From the IngeTrazo extension library

This describes the intended route once Dynamic Components is listed in the IngeTrazo community catalog. Until then, use [section B](#b-manual-installation).

1. In IngeTrazo open **Extensions → Manage extensions…**.
2. On the **Browse** tab, type `Dynamic` in the search field and select the entry. It shows the version, licence and a link to the repository.
3. Press **Download** (the button reads **Update** when a newer version exists). Community entries that are not on the maintainers' reviewed list are labelled as unreviewed and ask for confirmation first. Extensions are Python code: install only what you trust.
4. Restart IngeTrazo ("Restart required to apply changes").
5. The **Installed** tab lists it with **Update**, **Disable** and **Uninstall**.

For maintainers: the catalog expects a ZIP with exactly one top-level folder, `dynamic_components/`. The host checks the download against the SHA-256 in the catalog. `scripts/package.py` builds `dist/dynamic_components-<version>.zip` in that form with a reproducible hash. See [AGENTS.md](../AGENTS.md#releasing).

## B. Manual installation

### Plugin folder per installation

**Extensions → Open plugins folder** in IngeTrazo creates and opens it. Otherwise:

| Installation | Plugin folder |
|---|---|
| Windows | `%APPDATA%\IngeTrazo\plugins\` |
| Linux | `~/.local/share/ingetrazo/plugins/` (honours `$XDG_DATA_HOME`) |
| Linux, Flatpak | `~/.var/app/com.ingetrazo.IngeTrazo/data/ingetrazo/plugins/` |

IngeTrazo runs what is in that folder; it does not follow a checkout. After a change, copy again and restart.

### What to copy

The folder `dynamic_components/` (the package, not the whole repository) into the plugin folder, so that `…/plugins/dynamic_components/__init__.py` exists. Nothing else is needed.

### From the release zip

Download `dynamic_components-<version>.zip` from the [releases](https://github.com/d1rty-pixel/ingetrazo-dynamic-components/releases) and unpack it into the plugin folder. It holds exactly one folder, `dynamic_components/`.

```bash
# Linux
unzip dynamic_components-0.1.0.zip -d ~/.local/share/ingetrazo/plugins/
```

```powershell
# Windows
Expand-Archive dynamic_components-0.1.0.zip -DestinationPath "$env:APPDATA\IngeTrazo\plugins"
```

### From a checkout with the helper script

```bash
scripts/install-local.sh                 # finds the plugin folder (on WSL: the Windows one)
scripts/install-local.sh <plugins-dir>   # or name it
```

The script replaces `dynamic_components/` and keeps the previous copy as `.dynamic_components.bak`.

### Update and uninstall

- **Update:** use **Update** in the library, or install again (the script replaces the folder; by hand, delete the old `dynamic_components/` first so removed files do not linger), then restart IngeTrazo.
- **Uninstall:** use **Uninstall** in the library, or close IngeTrazo and delete the folder `dynamic_components/` from the plugin folder. Documents keep their dynamic components as plain components with their geometry; the definitions stay in the file and work again when you reinstall.

## C. Verify

1. Restart IngeTrazo.
2. Open **Window → Panels**: **Dynamic Components** is in the list.
3. Open `models/system32-cabinet/system32-cabinet.igz`, select the cabinet and open the tab: the options (width, height, plinth, shelves …) appear.

If the extension fails to load, the host lists it with a load error (Extensions → Manage extensions…, **Installed** tab, **View load error**) and still starts. If it is not listed at all, check the plugin folder path in the table and that IngeTrazo is 0.6.0 or later.
