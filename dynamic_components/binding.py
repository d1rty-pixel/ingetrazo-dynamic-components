"""Bind dynamic-component specs to the IngeTrazo model (groups, xforms, undo)."""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import math
import re
import uuid

from PySide6.QtGui import QMatrix4x4, QVector3D

from core.group import Group, _local_points, copy_group
from core.history import Command

from . import evaluate as _evaluate
from . import formula, spec as _spec
from . import generators as _gen
from . import geometry as _geo
from .messages import Msg

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
        # A pasted or imported instance: it brings its own copy.
        found = group.ext[KEY].get("spec")
        if not isinstance(found, dict):
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
    for g in instances_of(scene, def_id):
        g.ext[KEY]["spec"] = copy.deepcopy(data["defs"][def_id])


def _carry(scene, group, spec) -> None:
    """Keep the instance's own copy of its definition current, and give a
    document that lacks the definition (a pasted instance) a registry entry."""
    rec = group.ext[KEY]
    if rec.get("spec") != spec:
        rec["spec"] = copy.deepcopy(spec)
    data = scene.plugin_data.setdefault(KEY, {"version": 1, "defs": {}})
    data.setdefault("defs", {}).setdefault(rec["def"], copy.deepcopy(spec))


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


def make_dynamic(scene, group, spec=None, names=None) -> str:
    if group.xform is None:
        raise ValueError(Msg("Only a component instance can be made dynamic."))
    if is_dynamic(group):
        raise ValueError(Msg("The component is already dynamic."))
    children = list(group.children or ())
    if names is not None and len(names) != len(children):
        raise ValueError("names must match the children")
    spec = copy.deepcopy(spec) if spec else {"version": 1, "name": group.name}
    nodes = spec.setdefault("nodes", {})
    nodes.setdefault("", {"attrs": {}}).setdefault("attrs", {})
    nodes[""]["rest"] = {"size": _size(group)}
    taken = {""}
    for i, child in enumerate(children):
        if child.xform is None:
            child.xform = QMatrix4x4()
            child.component = False
        name = _unique_name(names[i] if names is not None else child.name, taken)
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
    group.ext[KEY] = {"def": def_id, "set": {}, "last": {},
                      "spec": copy.deepcopy(registry(scene)[def_id])}
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


def _write(scene, group, result, spec=None, *, regenerate=False, force=False,
           report=None) -> list:
    """Write a Result into the instance's children (no evaluation); returns
    the children whose placement it set. ``regenerate``: build the meshes of
    generated parts whose inputs changed (``force``: also those edited by
    hand); otherwise they are only placed, scaled from the size they were
    built for. ``report`` collects generation problems: node -> [Msg]."""
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
    placed: dict[str, list] = {}
    for name, part in parts:
        rebuilt.append(part)
        placements = result.placements.get(name)
        node = nodes.get(name, {})
        rest = node.get("rest")
        if not placements or not rest or "xform" not in rest:
            continue
        for p in placements:
            target = part
            if p.copy:
                target = existing.get((name, p.copy))
                if target is None:
                    target = copy_group(part, _in_definition=True)
                    record = {"part": name, "copy": p.copy}
                    if _gen_record(part) is not None:
                        record["gen"] = copy.deepcopy(_gen_record(part))
                    target.ext = {**(part.ext or {}), KEY: record}
                rebuilt.append(target)
            target.xform = _compose(rest["xform"], _frame_size(target, node), p)
            _style(scene, target, p)
            _mark_cutter(target, bool(node.get("cut")))
            placed.setdefault(name, []).append((target, p))
            written.append(target)
    group.children = rebuilt
    if regenerate and spec:
        _generate(spec, result, placed, report if report is not None else {}, force)
    return written


# ------------------------------------------------------------ generated parts

def _gen_record(g):
    rec = (g.ext or {}).get(KEY)
    gen = rec.get("gen") if isinstance(rec, dict) else None
    return gen if isinstance(gen, dict) else None


def _valid_size(value) -> bool:
    return (isinstance(value, list) and len(value) == 3
            and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                    and math.isfinite(v) and v > 0 for v in value))


def _frame_size(target, node) -> list:
    """The size the target's mesh stands for: what a generated mesh was
    built for, else the part's rest size."""
    if node.get("gen"):
        rec = _gen_record(target)
        if rec is not None and _valid_size(rec.get("lens")):
            return [float(v) for v in rec["lens"]]
    return node["rest"]["size"]


def _set_record(g, **fields) -> None:
    ext = dict(g.ext or {})
    rec = dict(ext.get(KEY) or {})
    for key, value in fields.items():
        if value is None:
            rec.pop(key, None)
        else:
            rec[key] = value
    ext[KEY] = rec
    g.ext = ext


def _mark_cutter(g, is_cutter: bool) -> None:
    """A cutter is a tool: never drawn. A part that stops being one is shown."""
    rec = (g.ext or {}).get(KEY) or {}
    if is_cutter:
        g.hidden = True
        if not rec.get("cutter"):
            _set_record(g, cutter=True)
    elif rec.get("cutter"):
        g.hidden = False
        _set_record(g, cutter=None)


def _cutter_box(g):
    """The cutter's local bounding box as 8 corners in the instance's frame,
    and its kind (a plain box cuts a rectangle, anything else a circle)."""
    pts = _local_points(g.mesh)
    if pts is None or len(pts) == 0:
        return None
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    xf = g.xform if g.xform is not None else QMatrix4x4()
    corners = []
    for i in range(8):
        c = QVector3D(float(hi[0] if i & 1 else lo[0]), float(hi[1] if i & 2 else lo[1]),
                      float(hi[2] if i & 4 else lo[2]))
        m = xf.map(c)
        corners.append((m.x(), m.y(), m.z()))
    kind = _geo.RECT if len(g.mesh.faces) <= 6 else _geo.ROUND
    return corners, kind


def _local_box(corners, inverse):
    """The corners in a board's frame as (lo, hi); None when the box is
    turned against the board (not by a multiple of 90°)."""
    pts = [inverse.map(QVector3D(*c)) for c in corners]
    xyz = [(q.x(), q.y(), q.z()) for q in pts]
    lo = [min(p[i] for p in xyz) for i in range(3)]
    hi = [max(p[i] for p in xyz) for i in range(3)]
    tol = 1e-6 * max(1.0, *[abs(v) for v in lo + hi])
    for p in xyz:
        for i in range(3):
            if min(abs(p[i] - lo[i]), abs(p[i] - hi[i])) > tol:
                return None
    return lo, hi


def _largest_face_paint(mesh) -> dict:
    best, area = None, -1.0
    for face in mesh.faces:
        try:
            a = sum(QVector3D.crossProduct(t1 - t0, t2 - t0).length()
                    for t0, t1, t2 in face.triangulate()) / 2
        except Exception:  # noqa: BLE001 - a broken face has no say
            continue
        if a > area:
            best, area = face, a
    return _gen.clean_paint(best.attrs) if best is not None else {}


def _round9(values):
    return [round(float(v), 9) for v in values]


def _generate(spec, result, placed, report, force) -> int:
    nodes = spec["nodes"]
    cutters: dict[str, list[str]] = {}
    for name, node in nodes.items():
        if node.get("cut"):
            cutters.setdefault(node["cut"], []).append(name)
    built = 0
    for name, node in nodes.items():
        gen = node.get("gen")
        if not gen or name not in placed:
            continue
        if not _gen.known(gen):
            report.setdefault(name, []).append(
                Msg("Unknown generator {name}: the part keeps its last shape", name=gen))
            continue
        boxes = []
        for cname in cutters.get(name, ()):
            for target, p in placed.get(cname, ()):
                if p.hidden:
                    continue
                box = _cutter_box(target)
                if box is not None:
                    boxes.append((cname, box))
        reached = {c: False for c, _ in boxes}
        params = dict(result.values.get(name, {}))
        for target, p in placed[name]:
            if p.hidden:
                continue
            built += _generate_one(target, name, node, gen, p, boxes, params,
                                   reached, report, force)
        for cname, ok in reached.items():
            if not ok:
                report.setdefault(cname, []).append(
                    Msg("Cuts nothing: no placement of it reaches {target}",
                        target=node.get("label") or name))
    return built


def _generate_one(target, name, node, gen, p, boxes, params, reached, report,
                  force) -> int:
    rest = node["rest"]
    size0 = rest["size"]
    lens = [getattr(p, a) if getattr(p, a) is not None else size0[j]
            for j, a in enumerate(("lenx", "leny", "lenz"))]
    if any(not math.isfinite(v) or v <= 1e-7 for v in lens):
        report.setdefault(name, []).append(
            Msg("The part has no volume; it keeps its last shape"))
        return 0
    record = _gen_record(target)
    if record is not None and isinstance(record.get("anchor"), list) \
            and len(record["anchor"]) == 3:
        anchor = [float(v) for v in record["anchor"]]
        paint = record.get("paint") if isinstance(record.get("paint"), dict) else {}
    else:                                   # first time: from the modelled mesh
        pts = _local_points(target.mesh)
        low = pts.min(axis=0) if pts is not None and len(pts) else [0.0, 0.0, 0.0]
        anchor = [float(low[j]) / size0[j] if size0[j] else 0.0 for j in range(3)]
        paint = _largest_face_paint(target.mesh)
    origin = [anchor[j] * lens[j] for j in range(3)]
    frame = _compose(rest["xform"], lens, p)
    inverse, ok = frame.inverted()
    if not ok:
        report.setdefault(name, []).append(
            Msg("The part's placement cannot be inverted"))
        return 0
    cuts, owners = [], []
    for cname, (corners, kind) in boxes:
        local = _local_box(corners, inverse)
        if local is None:
            msg = Msg("The cutter is turned against the board; only quarter turns work")
            if msg not in report.setdefault(cname, []):
                report[cname].append(msg)
            reached[cname] = True
            continue
        cuts.append(_geo.Box(tuple(local[0]), tuple(local[1]), kind))
        owners.append(cname)
    key = hashlib.sha1(json.dumps(
        [gen, _round9(lens), _round9(origin),
         [[_round9(c.lo), _round9(c.hi), c.kind] for c in cuts], paint],
        sort_keys=True).encode()).hexdigest()
    fp_now = _gen.fingerprint(target.mesh)
    if record is not None and record.get("fp") != fp_now and not force:
        msg = Msg("Edited by hand: the formulas no longer shape it. Regenerate to "
                  "apply them (the edits are lost).")
        if msg not in report.setdefault(name, []):
            report[name].append(msg)
        for cname in owners:
            reached[cname] = True
        return 0
    if record is not None and record.get("key") == key and record.get("fp") == fp_now:
        target.xform = frame
        _report_issues(record.get("issues"), owners, reached, report)
        return 0
    hit = _gen.cached(key)
    if hit is not None:
        mesh, issues = hit
    else:
        try:
            shape = _gen.build(gen, lens, origin, cuts, params)
        except _geo.GeometryError as exc:
            report.setdefault(name, []).append(exc.msg)
            return 0
        mesh = _gen.to_mesh(shape, paint)
        issues = [[i, (m if isinstance(m, Msg) else Msg(str(m))).to_json()]
                  for i, m in shape.issues]
        _gen.remember(key, (mesh, issues))
    stored = [[owners[i], m] for i, m in issues if 0 <= i < len(owners)]
    target.mesh = mesh
    target.xform = frame
    _set_record(target, gen={"key": key, "lens": [float(v) for v in lens],
                             "anchor": anchor, "fp": _gen.fingerprint(mesh),
                             "paint": paint, "issues": stored})
    _report_issues(stored, owners, reached, report)
    return 1


_MISSES = "The cut does not reach the board"


def _report_issues(issues, owners, reached, report) -> None:
    """Problems of the cutters, from a build; a cutter that missed every
    board copy is reported by the caller."""
    missed: dict[str, int] = {}
    for item in issues or ():
        if not isinstance(item, list) or len(item) != 2:
            continue
        cname, data = item
        msg = Msg.from_json(data)
        if msg is None or not isinstance(cname, str):
            continue
        if msg.template == _MISSES:
            missed[cname] = missed.get(cname, 0) + 1
            continue
        if msg not in report.setdefault(cname, []):
            report[cname].append(msg)
    total: dict[str, int] = {}
    for cname in owners:
        total[cname] = total.get(cname, 0) + 1
    for cname, count in total.items():
        if missed.get(cname, 0) < count:
            reached[cname] = True


def _store_problems(group, report) -> None:
    rec = group.ext[KEY]
    clean = {node: [m.to_json() for m in msgs] for node, msgs in report.items() if msgs}
    if clean:
        rec["problems"] = clean
    else:
        rec.pop("problems", None)


def apply(scene, group):
    spec = definition(scene, group)
    if spec is None:
        raise ValueError(Msg("Not a dynamic component, or its definition is missing."))
    rec = group.ext[KEY]
    _carry(scene, group, spec)
    result = _evaluate.evaluate(spec, copy.deepcopy(rec.get("set") or {}),
                                rec.get("last"))
    report: dict = {}
    _write(scene, group, result, spec, regenerate=True, report=report)
    rec["last"] = _json_safe(result.values)
    _store_problems(group, report)
    return result


def regenerate(scene, group) -> int:
    """Apply, rebuilding generated parts edited by hand too (their edits are
    lost); returns how many meshes were replaced."""
    spec = definition(scene, group)
    if spec is None:
        raise ValueError(Msg("Not a dynamic component, or its definition is missing."))
    rec = group.ext[KEY]
    _carry(scene, group, spec)
    result = _evaluate.evaluate(spec, copy.deepcopy(rec.get("set") or {}),
                                rec.get("last"))
    report: dict = {}
    before = {id(c): c.mesh for c in group.children or ()}
    _write(scene, group, result, spec, regenerate=True, force=True, report=report)
    rec["last"] = _json_safe(result.values)
    _store_problems(group, report)
    return sum(1 for c in group.children or () if before.get(id(c)) is not c.mesh)


def problems(group) -> dict:
    """Generation problems stored at the last apply, by part name."""
    raw = ((getattr(group, "ext", None) or {}).get(KEY) or {}).get("problems")
    out = {}
    if isinstance(raw, dict):
        for node, items in raw.items():
            if isinstance(node, str) and isinstance(items, list):
                msgs = [m for m in (Msg.from_json(i) for i in items[:50]) if m is not None]
                if msgs:
                    out[node] = msgs
    return out


def edited_parts(group) -> list:
    """Generated parts whose mesh no longer is what was generated."""
    names = []
    for child in group.children or ():
        record = _gen_record(child)
        if record is not None and record.get("fp") != _gen.fingerprint(child.mesh):
            name = _part_name(child)
            if name not in names:
                names.append(name)
    return names


_RESERVED_TYPES = {"hidden": "bool", "material": "string", "copies": "int",
                   "rotx": "float", "roty": "float", "rotz": "float"}


def set_values(scene, group, values):
    spec = definition(scene, group)
    if spec is None:
        raise ValueError(Msg("Not a dynamic component, or its definition is missing."))
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
        raise ValueError(Msg("Not a dynamic component, or its definition is missing."))
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
        expected = _compose(rest["xform"], _frame_size(child, spec["nodes"][name]),
                            placements[0])
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
        raise ValueError(Msg("Not a dynamic component, or its definition is missing."))
    def_id = group.ext[KEY]["def"]
    spec = copy.deepcopy(spec)
    gone = {n for n in names if n}
    for name in gone:
        spec["nodes"].pop(name, None)
    for node in spec["nodes"].values():
        if node.get("cut") in gone:
            node.pop("cut")             # no target any more: a plain part again
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
        return Msg("That is not a dynamic component.")
    groups = list(groups)
    if not groups:
        return Msg("Nothing to add.")
    up = _parents(scene)
    for g in groups:
        if g is root:
            return Msg("A component cannot be added to itself.")
        if is_dynamic(g):
            return Msg("{name} is a dynamic component itself; nested dynamic "
                       "components are not supported yet.", name=_shown(g))
        if _part_name(g) is not None:
            if up.get(id(g)) is root:
                return Msg("{name} is a part of this component already.", name=_shown(g))
            return Msg("{name} is a part of another dynamic component; "
                       "components keep their parts.", name=_shown(g))
        if getattr(g, "locked", False):
            return Msg("{name} is locked.", name=_shown(g))
        old = up.get(id(g))
        if old is not None and old is not root:
            from core import outliner
            if outliner.in_component(scene.groups, old):
                return Msg("{name} belongs to another component; components "
                           "keep their parts.", name=_shown(g))
    from core import outliner
    # reparent_problem answers "component" for a component target before it
    # looks at locks, so the target's lock is checked here.
    if outliner.locked_on_path(scene.groups, root):
        return Msg("The component is locked.")
    problem = outliner.reparent_problem(scene.groups, groups, root)
    if problem == "cycle":
        return Msg("The component sits inside what you want to add to it.")
    if problem == "locked":
        return Msg("The component is locked.")
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
    spec = definition(scene, group) or {"nodes": {}}
    tools = {n for n, node in spec["nodes"].items() if node.get("cut")}
    group.children = [c for c in group.children or ()
                      if _part_name(c) not in tools and not c.hidden
                      and not ((c.ext or {}).get(KEY) or {}).get("cutter")]
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
                    copy.deepcopy(g.ext), g.component, g.mesh))
        return {"groups": list(scene.groups), "state": state,
                "data": copy.deepcopy(scene.plugin_data.get(KEY))}

    @staticmethod
    def _restore(scene, s) -> None:
        scene.groups[:] = s["groups"]
        for g, xform, kids, hidden, material, ext, component, mesh in s["state"]:
            g.component = component
            g.mesh = mesh
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
