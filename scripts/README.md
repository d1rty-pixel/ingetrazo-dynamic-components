# Scripts

| Script | What it does |
|---|---|
| `install-local.sh [plugins-dir]` | Copies `dynamic_components/` into IngeTrazo's plugin folder (on WSL the Windows one, else the Linux one) and keeps the previous copy as `.dynamic_components.bak`. Restart IngeTrazo afterwards. |
| `package.py` | Builds `dist/dynamic_components-<version>.zip`: exactly one folder, `dynamic_components/`, as the IngeTrazo catalog requires; no caches or per-machine files; a fixed timestamp makes the hash reproducible. Prints the path; hash it with `sha256sum`. |
| `catalog-entry.toml` | The catalog entry to copy to `extensions/dynamic_components.toml` in the [ingetrazo-extensions](https://github.com/d1rty-pixel/ingetrazo-extensions) repository when listing a release. |

The model builder is not here but next to its model: [`models/system32-cabinet/build.py`](../models/system32-cabinet/README.md).
