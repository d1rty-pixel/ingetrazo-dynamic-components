"""Bind dynamic-component specs to the IngeTrazo model (groups, xforms, undo)."""
from __future__ import annotations

import copy
import json
import logging
import math
import uuid

from PySide6.QtGui import QMatrix4x4

from core.group import Group, _local_points, copy_group
from core.history import Command

from . import evaluate as _evaluate
from . import formula, spec as _spec

_log = logging.getLogger(__name__)

KEY = "dynamic_components"
AXES = ("x", "y", "z")
_EPS = 1e-9


# ---------------------------------------------------------------- registry

def registry(scene) -> dict:
    data = scene.plugin_data.get(KEY) or {}
    return dict(data.get("defs") or {})


def is_dynamic(group) -> bool:
    rec = (getattr(group, "ext", None) or {}).get(KEY)
    return isinstance(rec, dict) and "def" in rec


def definition(scene, group) -> dict | None:
    if not is_dynamic(group):
        return None
    found = registry(scene).get(group.ext[KEY]["def"])
    if found is None:
        return None
    # The registry comes from a document we may not have written: re-validate.
    try:
        return _spec.normalize(found)
    except _spec.SpecError:
        _log.warning("Ignoring an invalid dynamic component definition")
        return None


def _walk(groups):
    for g in groups:
        yield g
        yield from _walk(g.children or ())


def instances_of(scene, def_id) -> list:
    return [g for g in _walk(scene.groups)
            if is_dynamic(g) and g.ext[KEY]["def"] == def_id]


def _store_def(scene, def_id, spec) -> None:
    data = scene.plugin_data.setdefault(KEY, {"version": 1, "defs": {}})
    data.setdefault("defs", {})[def_id] = _spec.normalize(spec)


# ------------------------------------------------------------ matrix helpers

def _from_data(d) -> QMatrix4x4:
    """Build from QMatrix4x4.data() order (column-major); the constructor is row-major."""
    return QMatrix4x4([d[c * 4 + r] for r in range(4) for c in range(4)])


def _decompose(xform):
    d = list(xform.data())
    cols = [d[0:3], d[4:7], d[8:11]]
    return cols, d[12:15]


def _norm(v) -> float:
    return math.sqrt(sum(c * c for c in v))


def _local_cloud(group):
    """Points of the group's own mesh and nested placements, in its local coordinates."""
    import numpy as np
    parts = []
    pts = _local_points(group.mesh)
    if pts is not None:
        parts.append(pts)
    for child in group.children or ():
        sub = _local_cloud(child)
        if sub is None:
            continue
        if child.xform is not None:
            d = child.xform.data()
            rot = np.array([[d[0], d[4], d[8]], [d[1], d[5], d[9]],
                            [d[2], d[6], d[10]]])
            sub = sub @ rot.T + np.array([d[12], d[13], d[14]])
        parts.append(sub)
    return np.concatenate(parts) if parts else None


def _size(group) -> list[float]:
    cloud = _local_cloud(group)
    if cloud is None or len(cloud) == 0:
        return [0.0, 0.0, 0.0]
    return [float(v) for v in cloud.max(axis=0) - cloud.min(axis=0)]


def _compose(rest_xform, size, p) -> QMatrix4x4:
    cols, t0 = _decompose(_from_data(rest_xform))
    t = [getattr(p, a) if getattr(p, a) is not None else t0[i]
         for i, a in enumerate(AXES)]
    rot = [p.rotx, p.roty, p.rotz]
    if any(r is not None for r in rot):
        norms = [_norm(c) for c in cols]
        r = QMatrix4x4()
        # Rz·Ry·Rx; whether SketchUp uses the same order is unverified.
        r.rotate(rot[2] or 0.0, 0, 0, 1)
        r.rotate(rot[1] or 0.0, 0, 1, 0)
        r.rotate(rot[0] or 0.0, 1, 0, 0)
        rd = list(r.data())
        cols = [[c * norms[j] for c in rd[j * 4:j * 4 + 3]] for j in range(3)]
    lens = [p.lenx, p.leny, p.lenz]
    for j in range(3):
        if lens[j] is not None and size[j]:
            cols[j] = [c * lens[j] / size[j] for c in cols[j]]
    return _from_data(cols[0] + [0.0] + cols[1] + [0.0] + cols[2] + [0.0]
                      + t + [1.0])


def _resolve_material(scene, name):
    if not name:
        return None
    mats = scene.materials
    mat = mats.get(name)
    if mat is None:
        low = str(name).lower()
        mat = next((m for k, m in mats.items() if str(k).lower() == low), None)
    return dict(mat.face_attrs()) if mat is not None else None


# ------------------------------------------------------------------ make

def _unique_name(base, taken) -> str:
    base = (base or "part").strip().lower() or "part"
    if base in ("parent", "self"):
        base += "_part"
    name, n = base, 2
    while name in taken:
        name, n = f"{base}_{n}", n + 1
    return name


def make_dynamic(scene, group, spec=None) -> str:
    if group.xform is None:
        raise ValueError("Only a component instance can be made dynamic.")
    if is_dynamic(group):
        raise ValueError("The component is already dynamic.")
    spec = copy.deepcopy(spec) if spec else {"version": 1, "name": group.name}
    nodes = spec.setdefault("nodes", {})
    nodes.setdefault("", {"attrs": {}}).setdefault("attrs", {})
    nodes[""]["rest"] = {"size": _size(group)}
    taken = {""}
    for child in group.children or ():
        if child.xform is None:
            child.xform = QMatrix4x4()
            child.component = False
        name = _unique_name(child.name, taken)
        taken.add(name)
        child.ext = dict(child.ext or {})
        child.ext[KEY] = {"part": name}
        node = nodes.setdefault(name, {"attrs": {}})
        node.setdefault("attrs", {})
        node["rest"] = {"xform": [float(v) for v in child.xform.data()],
                        "size": _size(child)}
    def_id = uuid.uuid4().hex
    _store_def(scene, def_id, spec)
    group.ext = dict(group.ext or {})
    group.ext[KEY] = {"def": def_id, "set": {}, "last": {}}
    return def_id


# ----------------------------------------------------------------- apply

def _json_safe(values):
    return json.loads(json.dumps(values, default=str))


def _part_name(g):
    rec = (g.ext or {}).get(KEY)
    return rec.get("part") if isinstance(rec, dict) else None


def _is_copy(g) -> bool:
    return "copy" in (g.ext or {}).get(KEY, {})


def _style(scene, g, p) -> None:
    if p.hidden is not None:
        g.hidden = bool(p.hidden)
    paint = _resolve_material(scene, p.material)
    if paint is not None:
        g.material = paint


def _write(scene, group, result, spec=None) -> None:
    """Write a Result into the instance's children (no evaluation)."""
    spec = spec if spec is not None else definition(scene, group)
    nodes = (spec or {}).get("nodes", {})
    existing: dict[tuple, Group] = {}
    parts: list = []
    others: list = []
    for child in group.children or ():
        name = _part_name(child)
        if name is None:
            others.append(child)
        elif _is_copy(child):
            existing[(name, child.ext[KEY]["copy"])] = child
        else:
            parts.append((name, child))
    rebuilt = list(others)
    for name, part in parts:
        rebuilt.append(part)
        placements = result.placements.get(name)
        rest = nodes.get(name, {}).get("rest")
        if not placements or not rest or "xform" not in rest:
            continue
        for p in placements:
            target = part
            if p.copy:
                target = existing.get((name, p.copy))
                if target is None:
                    target = copy_group(part, _in_definition=True)
                    target.ext = {**(part.ext or {}),
                                  KEY: {"part": name, "copy": p.copy}}
                rebuilt.append(target)
            target.xform = _compose(rest["xform"], rest["size"], p)
            _style(scene, target, p)
    group.children = rebuilt


def apply(scene, group):
    spec = definition(scene, group)
    if spec is None:
        raise ValueError("Not a dynamic component, or its definition is missing.")
    rec = group.ext[KEY]
    result = _evaluate.evaluate(spec, copy.deepcopy(rec.get("set") or {}),
                                rec.get("last"))
    _write(scene, group, result, spec)
    rec["last"] = _json_safe(result.values)
    return result


_RESERVED_TYPES = {"hidden": "bool", "material": "string", "copies": "int",
                   "rotx": "float", "roty": "float", "rotz": "float"}


def set_values(scene, group, values):
    spec = definition(scene, group)
    if spec is None:
        raise ValueError("Not a dynamic component, or its definition is missing.")
    store = group.ext[KEY].setdefault("set", {})
    for node, attrs in values.items():
        if node not in spec["nodes"]:
            raise KeyError(f"unknown node {node!r}")
        for name, value in attrs.items():
            name = name.lower()
            if value is None:
                store.get(node, {}).pop(name, None)
                continue
            attr = spec["nodes"][node].get("attrs", {}).get(name)
            if attr is None:
                if name not in _spec.RESERVED:
                    raise KeyError(f"unknown attribute {name!r} on {node!r}")
                attr = {"type": _RESERVED_TYPES.get(name, "length")}
            store.setdefault(node, {})[name] = _spec.coerce(attr, value)
    return apply(scene, group)


def set_definition(scene, def_id, spec) -> None:
    _store_def(scene, def_id, spec)
    for g in instances_of(scene, def_id):
        apply(scene, g)


# ----------------------------------------------------------- scale / bake

def _uses_axes(spec) -> set[int]:
    used = set()
    for node, body in spec["nodes"].items():
        for attr in body.get("attrs", {}).values():
            src = attr.get("formula")
            if not src:
                continue
            try:
                refs = formula.parse(src).refs
            except formula.FormulaError:
                continue
            for ref_node, ref_attr in refs:
                for j, a in enumerate(AXES):
                    if ref_attr == "len" + a and (
                            (node and ref_node == "parent")
                            or (not node and ref_node == "self")):
                        used.add(j)
    return used


def absorbable_axes(scene, group) -> list[int]:
    """Axes (0=x, 1=y, 2=z) whose xform scale ``absorb_scale`` would take over;
    cheap enough for a document-changed hook, and empty means no undo step."""
    spec = definition(scene, group)
    if spec is None or group.xform is None:
        return []
    norms = [_norm(c) for c in _decompose(group.xform)[0]]
    return [j for j in sorted(_uses_axes(spec))
            if abs(norms[j] - 1.0) > 1e-6 and norms[j] > _EPS]


def absorb_scale(scene, group) -> bool:
    axes = absorbable_axes(scene, group)
    if not axes:
        return False
    spec = definition(scene, group)
    cols, t = _decompose(group.xform)
    norms = [_norm(c) for c in cols]
    inst = group.ext[KEY]
    store = inst.setdefault("set", {}).setdefault("", {})
    last = (inst.get("last") or {}).get("", {})
    rest = spec["nodes"][""].get("rest", {}).get("size", [0.0, 0.0, 0.0])
    for j in axes:
        attr = "len" + AXES[j]
        base = store.get(attr, last.get(attr, rest[j]))
        store[attr] = float(base) * norms[j]
        cols[j] = [c / norms[j] for c in cols[j]]
    group.xform = _from_data(cols[0] + [0.0] + cols[1] + [0.0] + cols[2]
                             + [0.0] + t + [1.0])
    apply(scene, group)
    return True


def bake(scene, group) -> None:
    def strip(g):
        if g.ext and KEY in g.ext:
            g.ext = {k: v for k, v in g.ext.items() if k != KEY} or None
    strip(group)
    for child in group.children or ():
        strip(child)


# --------------------------------------------------------------- undo/redo

def _subtree(g):
    yield g
    for c in g.children or ():
        yield from _subtree(c)


class DynamicCommand(Command):
    keeps_paint = False
    keeps_groups = False

    def __init__(self, mutate, roots, label="Dynamic component") -> None:
        self.mutate = mutate
        self.roots = list(roots)
        self.label = label
        self.before = self.after = None
        self.error = None

    def _targets(self, scene) -> list:
        seen = {id(g): g for g in self.roots}
        for g in list(seen.values()):
            if is_dynamic(g):
                for other in instances_of(scene, g.ext[KEY]["def"]):
                    seen.setdefault(id(other), other)
        return list(seen.values())

    def _capture(self, scene) -> dict:
        state = []
        for root in self._targets(scene):
            for g in _subtree(root):
                state.append((
                    g,
                    QMatrix4x4(g.xform) if g.xform is not None else None,
                    list(g.children or ()), g.hidden,
                    dict(g.material) if g.material else None,
                    copy.deepcopy(g.ext), g.component))
        return {"groups": list(scene.groups), "state": state,
                "data": copy.deepcopy(scene.plugin_data.get(KEY))}

    @staticmethod
    def _restore(scene, s) -> None:
        scene.groups[:] = s["groups"]
        for g, xform, kids, hidden, material, ext, component in s["state"]:
            g.component = component
            g.xform = QMatrix4x4(xform) if xform is not None else None
            g.children = list(kids)
            g.hidden = hidden
            g.material = dict(material) if material else None
            g.ext = copy.deepcopy(ext)
        if s["data"] is None:
            scene.plugin_data.pop(KEY, None)
        else:
            scene.plugin_data[KEY] = copy.deepcopy(s["data"])

    def do(self, scene) -> None:
        if self.after is None:
            self.before = self._capture(scene)
            try:
                self.mutate(scene)
            except BaseException as exc:
                self._restore(scene, self.before)
                self.error = exc
                raise
            self.after = self._capture(scene)
        else:
            self._restore(scene, self.after)
        scene.version += 1

    def undo(self, scene) -> None:
        self._restore(scene, self.before)
        scene.version += 1


def run(viewport, mutate, roots, label="Dynamic component") -> None:
    """Execute ``mutate`` as one undo step; re-raises what it raised, which
    ``History.execute`` would otherwise only log."""
    cmd = DynamicCommand(mutate, roots, label)
    viewport.history.execute(cmd)
    if cmd.error is not None:
        raise cmd.error
    notify = getattr(viewport, "notify_scene_changed", None)
    if callable(notify):
        notify()
