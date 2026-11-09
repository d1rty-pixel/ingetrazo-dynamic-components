"""Bind dynamic-component specs to the IngeTrazo model (groups, xforms, undo)."""
from __future__ import annotations

import copy
import json
import logging
import math
import re
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
    # A part name is read in formulas (``Shelf_board!LenX``): letters, digits
    # and _ only, starting with a letter — «Group 1» becomes ``group_1``.
    base = re.sub(r"\W+", "_", (base or "").strip().lower()).strip("_")
    if not base:
        base = "part"
    elif base[0].isdigit() or base[0] == "_":
        base = "part_" + base
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


def _write(scene, group, result, spec=None) -> list:
    """Write a Result into the instance's children (no evaluation); returns
    the children whose placement it set."""
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
    written = []
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
            written.append(target)
    group.children = rebuilt
    return written


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


# --------------------------------------------------------- live preview

def _placements(group) -> list:
    return [(c, list(c.xform.data()) if c.xform is not None else None, c.hidden)
            for c in group.children or ()]


def _moved(before, group) -> bool:
    after = _placements(group)
    if len(before) != len(after):
        return True
    for (c0, x0, h0), (c1, x1, h1) in zip(before, after):
        if c0 is not c1 or h0 != h1 or (x0 is None) != (x1 is None):
            return True
        if x0 is not None and any(abs(a - b) > 1e-9 for a, b in zip(x0, x1)):
            return True
    return False


def preview_scale(scene, group) -> bool:
    axes = absorbable_axes(scene, group)
    if not axes:
        return False
    spec = definition(scene, group)
    rec = group.ext[KEY]
    norms = [_norm(c) for c in _decompose(group.xform)[0]]
    over = copy.deepcopy(rec.get("set") or {})
    root = over.setdefault("", {})
    last = (rec.get("last") or {}).get("", {})
    rest = spec["nodes"][""].get("rest", {}).get("size", [0.0, 0.0, 0.0])
    for j in axes:
        attr = "len" + AXES[j]
        root[attr] = float(root.get(attr, last.get(attr, rest[j]))) * norms[j]
    result = _evaluate.evaluate(spec, over, rec.get("last"))
    before = _placements(group)
    cancel = QMatrix4x4()
    cancel.scale(*[1.0 / norms[j] if j in axes else 1.0 for j in range(3)])
    for target in _write(scene, group, result, spec):
        target.xform = cancel * target.xform
    return _moved(before, group)


def relayout(scene, group) -> bool:
    spec = definition(scene, group)
    if spec is None:
        return False
    rec = group.ext[KEY]
    result = _evaluate.evaluate(spec, copy.deepcopy(rec.get("set") or {}),
                                rec.get("last"))
    before = _placements(group)
    _write(scene, group, result, spec)
    return _moved(before, group)


# ------------------------------------------------------------ new parts

def loose_children(group) -> list:
    if not is_dynamic(group):
        return []
    return [c for c in group.children or () if _part_name(c) is None]


def add_parts(scene, group, only=None) -> list[str]:
    spec = definition(scene, group)
    if spec is None:
        raise ValueError("Not a dynamic component, or its definition is missing.")
    spec = copy.deepcopy(spec)
    nodes = spec["nodes"]
    taken = set(nodes)
    added = []
    loose = loose_children(group)
    if only is not None:
        loose = [c for c in loose if any(c is g for g in only)]
    for child in loose:
        if child.xform is None:
            child.xform = QMatrix4x4()
            child.component = False
        name = _unique_name(child.name, taken)
        taken.add(name)
        child.ext = dict(child.ext or {})
        child.ext[KEY] = {"part": name}
        nodes[name] = {"label": child.name or name, "attrs": {},
                       "rest": {"xform": [float(v) for v in child.xform.data()],
                                "size": _size(child)}}
        added.append(name)
    if added:
        _store_def(scene, group.ext[KEY]["def"], spec)
    return added


# ------------------------------------------------ host edit context

def is_open(scene, group) -> bool:
    g = getattr(scene, "edit_group", None)
    if g is None:
        return False
    up = _parents(scene)
    while g is not None:
        if g is group:
            return True
        g = up.get(id(g))
    return False


def _close_matrix(a, b, tol=1e-6) -> bool:
    return all(abs(x - y) <= tol * max(1.0, abs(x), abs(y))
               for x, y in zip(a.data(), b.data()))


def settle(scene, group) -> bool:
    spec = definition(scene, group)
    if spec is None or group.xform is None:
        return False
    rec = group.ext[KEY]
    try:
        result = _evaluate.evaluate(spec, copy.deepcopy(rec.get("set") or {}),
                                    rec.get("last"))
    except Exception:  # noqa: BLE001 - an unreadable spec settles nothing
        return False
    frames = []
    for child in group.children or ():
        name = _part_name(child)
        if name is None or _is_copy(child) or child.xform is None:
            continue
        rest = spec["nodes"].get(name, {}).get("rest")
        placements = result.placements.get(name)
        if not rest or "xform" not in rest or not placements:
            continue
        expected = _compose(rest["xform"], rest["size"], placements[0])
        inverse, ok = expected.inverted()
        if ok:
            frames.append(child.xform * inverse)
    if not frames:
        return False
    best, votes = None, 0
    for f in frames:
        n = sum(1 for g in frames if _close_matrix(f, g))
        if n > votes:
            best, votes = f, n
    if votes * 2 < len(frames) or _close_matrix(best, QMatrix4x4()):
        return False
    down, ok = best.inverted()
    if not ok:
        return False
    group.xform = group.xform * best
    for child in group.children or ():
        child.xform = down * (child.xform if child.xform is not None else QMatrix4x4())
    return True


# --------------------------------------------------------- deleted parts

def present_parts(group) -> set:
    return {_part_name(c) for c in group.children or ()
            if _part_name(c) is not None and not _is_copy(c)}


def missing_parts(scene, group) -> list:
    spec = definition(scene, group)
    if spec is None:
        return []
    here = present_parts(group)
    return [n for n in spec["nodes"] if n and n not in here]


def remove_parts(scene, group, names) -> None:
    spec = definition(scene, group)
    if spec is None:
        raise ValueError("Not a dynamic component, or its definition is missing.")
    def_id = group.ext[KEY]["def"]
    spec = copy.deepcopy(spec)
    gone = {n for n in names if n}
    for name in gone:
        spec["nodes"].pop(name, None)
    _store_def(scene, def_id, spec)
    for inst in instances_of(scene, def_id):
        kept = []
        for child in inst.children or ():
            name = _part_name(child)
            if name in gone:
                if _is_copy(child):
                    continue                    # generated: goes with its part
                child.ext = {k: v for k, v in (child.ext or {}).items()
                             if k != KEY} or None
            kept.append(child)
        inst.children = kept
        apply(scene, inst)


def dynamic_roots(scene) -> list:
    return [g for g in _walk(scene.groups) if is_dynamic(g)]


def _parents(scene) -> dict:
    up = {}
    for g in _walk(scene.groups):
        for c in g.children or ():
            up[id(c)] = g
    return up


def holder(scene, group):
    parent = _parents(scene).get(id(group))
    return parent if parent is not None and is_dynamic(parent) else None


def _shown(group) -> str:
    return f"“{group.name or 'Group'}”"


def add_problem(scene, groups, root):
    if root is None or not is_dynamic(root) or definition(scene, root) is None:
        return "That is not a dynamic component."
    groups = list(groups)
    if not groups:
        return "Nothing to add."
    up = _parents(scene)
    for g in groups:
        if g is root:
            return "A component cannot be added to itself."
        if is_dynamic(g):
            return (f"{_shown(g)} is a dynamic component itself; nested dynamic "
                    "components are not supported yet.")
        if _part_name(g) is not None:
            if up.get(id(g)) is root:
                return f"{_shown(g)} is a part of this component already."
            return (f"{_shown(g)} is a part of another dynamic component; "
                    "components keep their parts.")
        if getattr(g, "locked", False):
            return f"{_shown(g)} is locked."
        old = up.get(id(g))
        if old is not None and old is not root:
            from core import outliner
            if outliner.in_component(scene.groups, old):
                return (f"{_shown(g)} belongs to another component; components "
                        "keep their parts.")
    from core import outliner
    # reparent_problem answers "component" for a component target before it
    # looks at locks, so the target's lock is checked here.
    if outliner.locked_on_path(scene.groups, root):
        return "The component is locked."
    problem = outliner.reparent_problem(scene.groups, groups, root)
    if problem == "cycle":
        return "The component sits inside what you want to add to it."
    if problem == "locked":
        return "The component is locked."
    # "component": the target is a component. The host keeps a component's
    # parts as they are; a dynamic one takes the group into its definition,
    # which is what this does, so that rule does not apply here.
    return None


class AddToComponentCommand(Command):
    """Move groups into a dynamic root without moving them in the world (the
    host's own ReparentGroupsCommand, as the Browser's drag and drop) and make
    them parts: one undo step."""

    keeps_paint = False
    keeps_groups = False

    def __init__(self, groups, root, label="Add to dynamic component") -> None:
        self.groups = list(groups)
        self.root = root
        self.label = label
        self.reparent = None
        self.added = []
        self.dynamic = DynamicCommand(self._register, [root], label)
        self.error = None

    def _register(self, scene):
        self.added = add_parts(scene, self.root, only=self.groups)

    def do(self, scene) -> None:
        from core import outliner
        from core.history import ReparentGroupsCommand
        if self.reparent is None:
            moving = outliner.needs_moving(scene.groups, self.groups, self.root)
            self.reparent = ReparentGroupsCommand(moving, self.root) if moving else False
        if self.reparent:
            self.reparent.do(scene)
        try:
            self.dynamic.do(scene)
        except BaseException as exc:
            if self.reparent:
                self.reparent.undo(scene)
            self.error = exc
            raise

    def undo(self, scene) -> None:
        self.dynamic.undo(scene)
        if self.reparent:
            self.reparent.undo(scene)


def add_to_component(viewport, groups, root, label="Add to dynamic component") -> list:
    problem = add_problem(viewport.scene, groups, root)
    if problem:
        raise ValueError(problem)
    cmd = AddToComponentCommand(groups, root, label)
    viewport.history.execute(cmd)
    if cmd.error is not None:
        raise cmd.error
    notify = getattr(viewport, "notify_scene_changed", None)
    if callable(notify):
        notify()
    return list(cmd.added)


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
