"""Definition spec: validation, normalisation and value coercion."""
from __future__ import annotations

import math
import re

MAX_NODES = 256
MAX_ATTRS = 256
MAX_OPTIONS = 256
MAX_TEXT = 64 * 1024
MAX_INT = 2 ** 63

TYPES = ("length", "float", "int", "bool", "string", "choice", "material")
ACCESS = ("none", "view", "textbox", "list")
_NUMERIC = ("length", "float", "int")

# Natural type of each reserved attribute; `copy` is read-only and never declared.
_RESERVED_TYPES = {
    "x": "length", "y": "length", "z": "length",
    "lenx": "length", "leny": "length", "lenz": "length",
    "rotx": "float", "roty": "float", "rotz": "float",
    "hidden": "bool", "material": "material", "copies": "int",
}
RESERVED = frozenset(_RESERVED_TYPES) | {"copy"}
_ROOT_LEN_AXES = ("lenx", "leny", "lenz")
_FORBIDDEN_PARTS = frozenset({"self", "parent"})

_NAME_RE = re.compile(r"^[^\W\d]\w*$")
_NUMERIC_TEXT = re.compile(r"^[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$")


class SpecError(Exception):
    """The spec or a value is invalid; the message is user-facing English text."""


# ------------------------------------------------------------------ helpers

def _number(value, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SpecError(f"{what} must be a number")
    try:
        result = float(value)
    except OverflowError:
        raise SpecError(f"{what} is out of range") from None
    if not math.isfinite(result):
        raise SpecError(f"{what} must be finite")
    return result


def _string(value, what: str, limit: int = MAX_TEXT) -> str:
    if not isinstance(value, str):
        raise SpecError(f"{what} must be text")
    if len(value) > limit:
        raise SpecError(f"{what} is too long")
    return value


def _scalar(value, what: str):
    """JSON-safe scalar: str, bool, int, finite float."""
    if isinstance(value, str):
        return _string(value, what)
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        if abs(value) > MAX_INT:
            raise SpecError(f"{what} is out of range")
        return value
    if isinstance(value, float):
        return _number(value, what)
    raise SpecError(f"{what} has an unsupported type ({type(value).__name__})")


def _same(a, b) -> bool:
    return isinstance(a, bool) == isinstance(b, bool) and a == b


def _format_number(value: float) -> str:
    if value == int(value) and abs(value) < 1e15:
        return str(int(value))
    return format(value, ".15g")


# ------------------------------------------------------------------- coerce

def _to_float(value) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, str):
        text = value.strip()
        if not _NUMERIC_TEXT.match(text):
            raise SpecError(f"{value[:30]!r} is not a number")
        return _number(float(text), "Value")
    return _number(value, "Value")


def _to_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return _number(value, "Value") != 0
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("true", "yes", "1"):
            return True
        if text in ("false", "no", "0"):
            return False
    raise SpecError("Expected true or false")


def _to_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return _format_number(_number(value, "Value"))
    return _string(value, "Text")


def _to_choice(attr: dict, value):
    value = _scalar(value, "Value")
    options = attr.get("options")
    if not options:
        return value
    for _, option in options:
        if _same(option, value):
            return option
    if isinstance(value, str):
        for _, option in options:
            if _to_text(option) == value:
                return option
    raise SpecError(f"{_to_text(value)[:30]!r} is not one of the options")


def _clamp(attr: dict, value: float) -> float:
    lo, hi = attr.get("min"), attr.get("max")
    if lo is not None:
        value = max(value, lo)
    if hi is not None:
        value = min(value, hi)
    return value


def coerce(attr: dict, value) -> object:
    """Convert `value` to the attribute's type, clamped to min/max; raises SpecError."""
    kind = attr.get("type")
    if kind in ("length", "float"):
        return float(_clamp(attr, _to_float(value)))
    if kind == "int":
        number = _clamp(attr, _to_float(value))
        if abs(number) > MAX_INT:
            raise SpecError("Value is out of range")
        return int(math.floor(number + 0.5))
    if kind == "bool":
        return _to_bool(value)
    if kind in ("string", "material"):
        return _to_text(value)
    if kind == "choice":
        return _to_choice(attr, value)
    raise SpecError(f"Unknown attribute type {kind!r}")


# ---------------------------------------------------------------- normalize

def _name(raw, what: str) -> str:
    name = _string(raw, what, 256).lower()
    if not _NAME_RE.match(name):
        raise SpecError(f"{what} {raw!r} is not a valid name")
    return name


def _options(raw) -> list:
    if not isinstance(raw, (list, tuple)):
        raise SpecError("options must be a list")
    if len(raw) > MAX_OPTIONS:
        raise SpecError(f"Too many options (limit {MAX_OPTIONS})")
    result = []
    for item in raw:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise SpecError("Each option must be a [label, value] pair")
        result.append([_string(item[0], "Option label"), _scalar(item[1], "Option value")])
    return result


def _bound(raw, what: str):
    return None if raw is None else _number(raw, what)


def _infer_type(name: str, value) -> str:
    if name in _RESERVED_TYPES:
        return _RESERVED_TYPES[name]
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, str):
        return "string"
    return "float"


def _default_value(attr: dict):
    kind = attr["type"]
    if kind == "choice" and attr.get("options"):
        return attr["options"][0][1]
    return {"bool": False, "int": 0, "string": "", "material": "", "choice": ""}.get(kind, 0.0)


def _attr(name: str, raw_name: str, raw, is_root: bool) -> dict:
    if name == "copy":
        raise SpecError("'copy' is read-only and cannot be declared")
    if not isinstance(raw, dict):
        raise SpecError(f"Attribute {raw_name!r} must be an object")
    kind = raw.get("type") or _infer_type(name, raw.get("value"))
    if kind not in TYPES:
        raise SpecError(f"Attribute {raw_name!r}: unknown type {kind!r}")
    if name in _RESERVED_TYPES and kind != _RESERVED_TYPES[name]:
        raise SpecError(f"Attribute {name!r} must have type {_RESERVED_TYPES[name]!r}")
    access = raw.get("access") or "none"
    if access not in ACCESS:
        raise SpecError(f"Attribute {raw_name!r}: unknown access {access!r}")
    formula = raw.get("formula") or None
    if formula is not None:
        formula = _string(formula, "Formula")
    attr = {"label": _string(raw.get("label") or raw_name, "Label", 1024), "type": kind,
            "value": None, "formula": formula, "access": access}
    if raw.get("options") is not None:
        attr["options"] = _options(raw["options"])
    for key in ("min", "max"):
        if raw.get(key) is not None:
            attr[key] = _bound(raw[key], key)
    if attr.get("min") is not None and attr.get("max") is not None and attr["min"] > attr["max"]:
        raise SpecError(f"Attribute {raw_name!r}: min is greater than max")
    value = raw.get("value")
    keep_open = is_root and name in _ROOT_LEN_AXES and value is None
    if not keep_open:
        attr["value"] = _default_value(attr) if value is None else coerce(attr, value)
    return attr


def _node(name: str, raw_name: str, raw, fallback_label: str) -> dict:
    if not isinstance(raw, dict):
        raise SpecError(f"Node {raw_name!r} must be an object")
    raw_attrs = {} if raw.get("attrs") is None else raw["attrs"]
    if not isinstance(raw_attrs, dict):
        raise SpecError(f"Node {raw_name!r}: attrs must be an object")
    if len(raw_attrs) > MAX_ATTRS:
        raise SpecError(f"Node {raw_name!r}: too many attributes (limit {MAX_ATTRS})")
    attrs = {}
    for attr_raw_name, attr_raw in raw_attrs.items():
        key = _name(attr_raw_name, "Attribute name")
        if key in attrs:
            raise SpecError(f"Duplicate attribute {key!r} in node {raw_name!r}")
        attrs[key] = _attr(key, attr_raw_name, attr_raw, name == "")
    label = _string(raw.get("label") or fallback_label, "Label", 1024)
    return {"label": label, "attrs": attrs, "rest": _rest(raw.get("rest"), raw_name)}


def _float_list(raw, count: int, what: str) -> list:
    if not isinstance(raw, (list, tuple)) or len(raw) != count:
        raise SpecError(f"{what} must be a list of {count} numbers")
    return [_number(v, what) for v in raw]


def _rest(raw, node_name: str) -> dict:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise SpecError(f"Node {node_name!r}: rest must be an object")
    rest = {}
    if raw.get("xform") is not None:
        rest["xform"] = _float_list(raw["xform"], 16, "rest xform")
    if raw.get("size") is not None:
        size = _float_list(raw["size"], 3, "rest size")
        if any(v < 0 for v in size):
            raise SpecError("rest size must not be negative")
        rest["size"] = size
    return rest


def normalize(spec: dict) -> dict:
    """Validated, lower-cased deep copy of `spec`; raises SpecError."""
    if not isinstance(spec, dict):
        raise SpecError("Spec must be an object")
    version = spec.get("version", 1)
    if isinstance(version, bool) or version != 1:
        raise SpecError(f"Unsupported spec version {version!r}")
    name = _string(spec.get("name", ""), "Name", 1024)
    raw_nodes = spec.get("nodes", {})
    if not isinstance(raw_nodes, dict):
        raise SpecError("nodes must be an object")
    if len(raw_nodes) > MAX_NODES:
        raise SpecError(f"Too many nodes (limit {MAX_NODES})")
    keyed = {}
    for raw_name, raw in raw_nodes.items():
        key = _string(raw_name, "Node name", 256).lower()
        if key and (not _NAME_RE.match(key) or key in _FORBIDDEN_PARTS):
            raise SpecError(f"Node name {raw_name!r} is not valid")
        if key in keyed:
            raise SpecError(f"Duplicate node {key!r}")
        keyed[key] = (raw_name, raw)
    nodes = {"": _node("", "", keyed.get("", (None, {}))[1], name)}
    for key, (raw_name, raw) in keyed.items():
        if key:
            nodes[key] = _node(key, raw_name, raw, raw_name)
    if len(nodes) > MAX_NODES:
        raise SpecError(f"Too many nodes (limit {MAX_NODES})")
    return {"version": 1, "name": name, "nodes": nodes}


def editable_attrs(spec: dict) -> list[tuple[str, str, dict]]:
    """(node, name, attr) with access textbox/list of a normalized spec, root first."""
    result = []
    for node, data in spec.get("nodes", {}).items():
        for name, attr in data.get("attrs", {}).items():
            if attr.get("access") in ("textbox", "list"):
                result.append((node, name, attr))
    return result
