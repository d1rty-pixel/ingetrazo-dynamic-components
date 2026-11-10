"""Definition spec: validation, normalisation and value coercion."""
from __future__ import annotations

import math
import re

from .messages import MessageError, Msg, N_

MAX_NODES = 256
MAX_ATTRS = 256
MAX_OPTIONS = 256
MAX_TEXT = 64 * 1024
MAX_INT = 2 ** 63

TYPES = ("length", "float", "int", "bool", "string", "choice", "material")
ACCESS = ("none", "view", "textbox", "list", "warn")
MAX_SECTION = 256
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
_GEN_RE = re.compile(r"^[a-z][a-z0-9_]*@[0-9]+$")
_NUMERIC_TEXT = re.compile(r"^[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$")


class SpecError(MessageError):
    """The spec or a value is invalid; ``.msg`` is a translatable Msg."""


# ------------------------------------------------------------------ helpers

def _number(value, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SpecError(Msg("{what} must be a number", what=what))
    try:
        result = float(value)
    except OverflowError:
        raise SpecError(Msg("{what} is out of range", what=what)) from None
    if not math.isfinite(result):
        raise SpecError(Msg("{what} must be finite", what=what))
    return result


def _string(value, what: str, limit: int = MAX_TEXT) -> str:
    if not isinstance(value, str):
        raise SpecError(Msg("{what} must be text", what=what))
    if len(value) > limit:
        raise SpecError(Msg("{what} is too long", what=what))
    return value


def _scalar(value, what: str):
    """JSON-safe scalar: str, bool, int, finite float."""
    if isinstance(value, str):
        return _string(value, what)
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        if abs(value) > MAX_INT:
            raise SpecError(Msg("{what} is out of range", what=what))
        return value
    if isinstance(value, float):
        return _number(value, what)
    raise SpecError(Msg("{what} has an unsupported type ({type})", what=what,
                            type=type(value).__name__))


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
            raise SpecError(Msg("{value} is not a number", value=repr(value[:30])))
        return _number(float(text), N_("Value"))
    return _number(value, N_("Value"))


def _to_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return _number(value, N_("Value")) != 0
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("true", "yes", "1"):
            return True
        if text in ("false", "no", "0"):
            return False
    raise SpecError(Msg("Expected true or false"))


def _to_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return _format_number(_number(value, N_("Value")))
    return _string(value, N_("Text"))


def _to_choice(attr: dict, value):
    value = _scalar(value, N_("Value"))
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
    raise SpecError(Msg("{value} is not one of the options", value=repr(_to_text(value)[:30])))


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
            raise SpecError(Msg("Value is out of range"))
        return int(math.floor(number + 0.5))
    if kind == "bool":
        return _to_bool(value)
    if kind in ("string", "material"):
        return _to_text(value)
    if kind == "choice":
        return _to_choice(attr, value)
    raise SpecError(Msg("Unknown attribute type {type}", type=repr(kind)))


# ---------------------------------------------------------------- normalize

def _name(raw, what: str) -> str:
    name = _string(raw, what, 256).lower()
    if not _NAME_RE.match(name):
        raise SpecError(Msg("{what} {name} is not a valid name", what=what, name=repr(raw)))
    return name


def _options(raw) -> list:
    if not isinstance(raw, (list, tuple)):
        raise SpecError(Msg("options must be a list"))
    if len(raw) > MAX_OPTIONS:
        raise SpecError(Msg("Too many options (limit {limit})", limit=MAX_OPTIONS))
    result = []
    for item in raw:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise SpecError(Msg("Each option must be a [label, value] pair"))
        result.append([_string(item[0], N_("Option label")), _scalar(item[1], N_("Option value"))])
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
        raise SpecError(Msg("'copy' is read-only and cannot be declared"))
    if not isinstance(raw, dict):
        raise SpecError(Msg("Attribute {name} must be an object", name=repr(raw_name)))
    kind = raw.get("type") or _infer_type(name, raw.get("value"))
    if kind not in TYPES:
        raise SpecError(Msg("Attribute {name}: unknown type {type}", name=repr(raw_name),
                            type=repr(kind)))
    if name in _RESERVED_TYPES and kind != _RESERVED_TYPES[name]:
        raise SpecError(Msg("Attribute {name} must have type {type}", name=repr(name),
                            type=repr(_RESERVED_TYPES[name])))
    access = raw.get("access") or "none"
    if access not in ACCESS:
        raise SpecError(Msg("Attribute {name}: unknown access {access}", name=repr(raw_name),
                            access=repr(access)))
    formula = raw.get("formula") or None
    if formula is not None:
        formula = _string(formula, N_("Formula"))
    attr = {"label": _string(raw.get("label") or raw_name, N_("Label"), 1024), "type": kind,
            "value": None, "formula": formula, "access": access}
    if raw.get("section"):
        attr["section"] = _string(raw["section"], N_("Section"), MAX_SECTION)
    if raw.get("show_if"):
        attr["show_if"] = _string(raw["show_if"], N_("Show-if formula"))
    if raw.get("options") is not None:
        attr["options"] = _options(raw["options"])
    for key in ("min", "max"):
        if raw.get(key) is not None:
            attr[key] = _bound(raw[key], key)
    if attr.get("min") is not None and attr.get("max") is not None and attr["min"] > attr["max"]:
        raise SpecError(Msg("Attribute {name}: min is greater than max", name=repr(raw_name)))
    value = raw.get("value")
    keep_open = is_root and name in _ROOT_LEN_AXES and value is None
    if not keep_open:
        attr["value"] = _default_value(attr) if value is None else coerce(attr, value)
    return attr


def _node(name: str, raw_name: str, raw, fallback_label: str) -> dict:
    if not isinstance(raw, dict):
        raise SpecError(Msg("Node {name} must be an object", name=repr(raw_name)))
    raw_attrs = {} if raw.get("attrs") is None else raw["attrs"]
    if not isinstance(raw_attrs, dict):
        raise SpecError(Msg("Node {name}: attrs must be an object", name=repr(raw_name)))
    if len(raw_attrs) > MAX_ATTRS:
        raise SpecError(Msg("Node {name}: too many attributes (limit {limit})",
                            name=repr(raw_name), limit=MAX_ATTRS))
    attrs = {}
    for attr_raw_name, attr_raw in raw_attrs.items():
        key = _name(attr_raw_name, N_("Attribute name"))
        if key in attrs:
            raise SpecError(Msg("Duplicate attribute {attr} in node {name}", attr=repr(key),
                                name=repr(raw_name)))
        attrs[key] = _attr(key, attr_raw_name, attr_raw, name == "")
    label = _string(raw.get("label") or fallback_label, N_("Label"), 1024)
    node = {"label": label, "attrs": attrs, "rest": _rest(raw.get("rest"), raw_name)}
    if raw.get("gen"):
        gen = _string(raw["gen"], N_("Generator"), 64).lower()
        if not name or not _GEN_RE.match(gen):
            raise SpecError(Msg("Node {name}: {gen} is not a valid generator name",
                                name=repr(raw_name), gen=repr(raw["gen"])))
        node["gen"] = gen
    if raw.get("cut"):
        if not name:
            raise SpecError(Msg("The component itself cannot cut"))
        node["cut"] = _string(raw["cut"], N_("Cut target"), 256).lower()
    return node


def _check_links(nodes: dict) -> None:
    """A cutter names an existing other part that is not a cutter itself."""
    for name, node in nodes.items():
        target = node.get("cut")
        if target is None:
            continue
        if node.get("gen"):
            raise SpecError(Msg("Part {name} cannot both be generated and cut",
                                name=repr(name)))
        if target == name or target not in nodes or not target:
            raise SpecError(Msg("Part {name} cuts {target}, which is not another part",
                                name=repr(name), target=repr(target)))
        if nodes[target].get("cut") is not None:
            raise SpecError(Msg("Part {name} cuts {target}, which is a cutter itself",
                                name=repr(name), target=repr(target)))


def _float_list(raw, count: int, what: str) -> list:
    if not isinstance(raw, (list, tuple)) or len(raw) != count:
        raise SpecError(Msg("{what} must be a list of {count} numbers", what=what, count=count))
    return [_number(v, what) for v in raw]


def _rest(raw, node_name: str) -> dict:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise SpecError(Msg("Node {name}: rest must be an object", name=repr(node_name)))
    rest = {}
    if raw.get("xform") is not None:
        rest["xform"] = _float_list(raw["xform"], 16, N_("rest xform"))
    if raw.get("size") is not None:
        size = _float_list(raw["size"], 3, N_("rest size"))
        if any(v < 0 for v in size):
            raise SpecError(Msg("rest size must not be negative"))
        rest["size"] = size
    return rest


def normalize(spec: dict) -> dict:
    """Validated, lower-cased deep copy of `spec`; raises SpecError."""
    if not isinstance(spec, dict):
        raise SpecError(Msg("Spec must be an object"))
    version = spec.get("version", 1)
    if isinstance(version, bool) or version != 1:
        raise SpecError(Msg("Unsupported spec version {version}", version=repr(version)))
    name = _string(spec.get("name", ""), N_("Name"), 1024)
    raw_nodes = spec.get("nodes", {})
    if not isinstance(raw_nodes, dict):
        raise SpecError(Msg("nodes must be an object"))
    if len(raw_nodes) > MAX_NODES:
        raise SpecError(Msg("Too many nodes (limit {limit})", limit=MAX_NODES))
    keyed = {}
    for raw_name, raw in raw_nodes.items():
        key = _string(raw_name, N_("Node name"), 256).lower()
        if key and (not _NAME_RE.match(key) or key in _FORBIDDEN_PARTS):
            raise SpecError(Msg("Node name {name} is not valid", name=repr(raw_name)))
        if key in keyed:
            raise SpecError(Msg("Duplicate node {name}", name=repr(key)))
        keyed[key] = (raw_name, raw)
    nodes = {"": _node("", "", keyed.get("", (None, {}))[1], name)}
    for key, (raw_name, raw) in keyed.items():
        if key:
            nodes[key] = _node(key, raw_name, raw, raw_name)
    if len(nodes) > MAX_NODES:
        raise SpecError(Msg("Too many nodes (limit {limit})", limit=MAX_NODES))
    _check_links(nodes)
    return {"version": 1, "name": name, "nodes": nodes}


def editable_attrs(spec: dict) -> list[tuple[str, str, dict]]:
    """(node, name, attr) with access textbox/list of a normalized spec, root first."""
    result = []
    for node, data in spec.get("nodes", {}).items():
        for name, attr in data.get("attrs", {}).items():
            if attr.get("access") in ("textbox", "list"):
                result.append((node, name, attr))
    return result
