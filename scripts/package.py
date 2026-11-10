"""Build a clean extension zip: exactly one folder, `dynamic_components/`, as the IngeTrazo catalog requires.

No caches, local paths, models, tests or per-machine files. The hash of the
result goes into the catalog entry, so build it once and upload that file.
"""
import re
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

root = Path(__file__).resolve().parents[1]
package = root / "dynamic_components"
version = re.search(r'__version__ = "([^"]+)"',
                    (package / "__init__.py").read_text(encoding="utf-8")).group(1)
out = root / "dist" / f"dynamic_components-{version}.zip"
out.parent.mkdir(exist_ok=True)
files = sorted(p for p in package.rglob("*")
               if p.is_file() and p.suffix in {".py", ".json"} and "__pycache__" not in p.parts)
with ZipFile(out, "w", ZIP_DEFLATED) as archive:
    for path in [*files, root / "LICENSE"]:
        name = ("dynamic_components/LICENSE" if path.name == "LICENSE"
                else path.relative_to(root).as_posix())
        # A fixed timestamp keeps the zip, and so its SHA-256, reproducible.
        info = ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
        info.compress_type, info.external_attr = ZIP_DEFLATED, 0o644 << 16
        archive.writestr(info, path.read_bytes())
print(out)
