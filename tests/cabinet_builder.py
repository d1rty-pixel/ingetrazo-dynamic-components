"""The System 32 cabinet's build script (models/system32-cabinet/build.py) as a
module; it is not part of the extension, the tests use it as their reference
dynamic component."""
import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "models" / "system32-cabinet" / "build.py"
_spec = importlib.util.spec_from_file_location("system32_cabinet_build", _PATH)
build = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build)
