"""Builds the System 32 cabinet model (system32-cabinet.igz); see README.md.

Not part of the extension: it only uses the extension's public binding API and
makes nothing a person could not make by hand in the interface. Part and attribute names are fixed English words because the
formulas read them; the labels are written in the language given to
``insert_cabinet`` (``labels.json`` holds de/es/fr) and are document content from
then on.

    python build.py [out.igz] [--lang de]
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from PySide6.QtGui import QMatrix4x4, QVector3D

_LABELS = json.loads((Path(__file__).with_name("labels.json")).read_text(encoding="utf-8"))
_lang = "en"


def tr(text: str) -> str:
    return _LABELS.get(_lang, {}).get(text, text)


# Starting size and boards (metres); everything else follows the formulas.
WIDTH, DEPTH, HEIGHT = 0.6, 0.56, 2.0
THICKNESS, BACK = 0.019, 0.008
HOLE_D, HOLE_DEPTH, RASTER = 0.005, 0.012, 0.032
SPLIT = 1.0           # a divider for every started metre of width
EDGE_MIN = 0.032      # smallest distance of the first/last hole to the panels

WOOD = {"color": (0.86, 0.74, 0.55), "opacity": 1.0}
BACK_PAINT = {"color": (0.93, 0.90, 0.83), "opacity": 1.0}
PLINTH_PAINT = {"color": (0.35, 0.33, 0.31), "opacity": 1.0}


def _attr(label, kind, value=None, formula=None, access="none", **extra) -> dict:
    attr = {"label": label, "type": kind, "value": value, "formula": formula,
            "access": access}
    attr.update({k: v for k, v in extra.items() if v is not None})
    return attr


def _quoted(text: str) -> str:
    return '"' + text.replace('"', '""') + '"'


def _placement(x, y, z, lenx, leny, lenz, **more) -> dict:
    attrs = {}
    for name, source in (("x", x), ("y", y), ("z", z), ("lenx", lenx),
                         ("leny", leny), ("lenz", lenz), *more.items()):
        kind = {"hidden": "bool", "copies": "int"}.get(name, "length")
        attrs[name] = _attr(name, kind, formula=source)
    return attrs


def cabinet_spec() -> dict:
    carcass, plinth, shelves, holes, dividers = (
        tr("Carcass"), tr("Plinth"), tr("Shelves"), tr("Holes (System 32)"),
        tr("Dividers"))
    no_fit = tr("Smallest and largest gap cannot both be kept at this height.")
    outside = tr("The gap between the shelves is outside the smallest/largest gap.")
    S = "Parent!Thickness"
    inner_w = f"=Parent!LenX - 2*{S}"
    # Where the shelves and dividers end: in front of the back panel's groove.
    shelf_depth = "IF(Parent!Back_Panel, Parent!Back_Y, Parent!LenY)"
    root = {
        # Carcass
        "lenx": _attr(tr("Width"), "length", access="textbox", min=0.2, max=2.4,
                      section=carcass),
        "leny": _attr(tr("Depth"), "length", access="textbox", min=0.15, max=0.9,
                      section=carcass),
        "lenz": _attr(tr("Height"), "length", access="textbox", min=0.3, max=2.8,
                      section=carcass),
        "thickness": _attr(tr("Board thickness"), "length", THICKNESS, access="list",
                           options=[["16 mm", 0.016], ["19 mm", 0.019], ["25 mm", 0.025]],
                           section=carcass),
        "back_panel": _attr(tr("Back panel"), "bool", True, access="textbox",
                            section=carcass),
        "back_thick": _attr(tr("Back panel thickness"), "length", BACK),
        "back_inset": _attr(tr("Back panel groove: distance from the rear edge"),
                            "length", 0.010, access="textbox", min=0.005, max=0.05,
                            section=carcass, show_if="=Back_Panel"),
        "groove_d": _attr(tr("Back panel groove: depth"), "length", 0.008,
                          access="textbox", min=0.003, max=0.012, section=carcass,
                          show_if="=Back_Panel"),
        # Plinth
        "plinth": _attr(tr("Plinth"), "bool", True, access="textbox", section=plinth),
        "plinth_h": _attr(tr("Plinth height"), "length", 0.1, access="textbox",
                          min=0.03, max=0.3, section=plinth, show_if="=Plinth"),
        "plinth_set": _attr(tr("Plinth set-back"), "length", 0.04, access="textbox",
                            min=0.0, max=0.2, section=plinth, show_if="=Plinth"),
        # Dividers
        "split": _attr(tr("Divider for every started width of"), "length", SPLIT,
                       access="textbox", min=0.4, max=3.0, section=dividers),
        "divs": _attr(tr("Number of dividers"), "int", 0, access="view", min=0,
                      section=dividers, formula="=MAX(0, CEILING(LenX/Split, 1) - 1)"),
        # Shelves
        "shelf_mode": _attr(tr("Number of shelves"), "choice", "auto", access="list",
                            options=[[tr("From the height"), "auto"],
                                     [tr("Fixed"), "fixed"]], section=shelves),
        "shelves": _attr(tr("Shelves"), "int", 3, access="textbox", min=0, max=30,
                         section=shelves, show_if='=Shelf_Mode="fixed"'),
        "gap_min": _attr(tr("Smallest gap"), "length", 0.18, access="textbox",
                         min=0.05, max=1.0, section=shelves),
        "gap_max": _attr(tr("Largest gap"), "length", 0.38, access="textbox",
                         min=0.08, max=2.0, section=shelves),
        "support": _attr(tr("Shelf support: hole centre to shelf"), "length", 0.0025,
                         access="textbox", min=-0.02, max=0.03, section=shelves),
        "n": _attr(tr("Shelves (from the height)"), "int", 0, access="view", min=0,
                   max=50, section=shelves, show_if='=Shelf_Mode="auto"',
                   formula='=IF(Shelf_Mode="auto", N_Min, Shelves)'),
        "gap": _attr(tr("Gap between shelves"), "length", 0.0, access="view",
                     section=shelves, formula="=(In_H - N*Thickness)/(N + 1)"),
        "warning": _attr(tr("Shelf warning"), "string", "", access="warn",
                         section=shelves, formula=(
                             f'=IF(AND(Shelf_Mode="auto", N_Min > N_Max), {_quoted(no_fit)}, '
                             f'IF(AND(Shelf_Mode="fixed", OR(Gap < Gap_Min, Gap > Gap_Max)), '
                             f'{_quoted(outside)}, ""))')),
        # Holes
        "drill": _attr(tr("Drill hole rows"), "bool", True, access="textbox",
                       section=holes),
        "row_front": _attr(tr("Front row from the front edge"), "length", 0.037,
                           access="textbox", min=0.01, max=0.2, section=holes,
                           show_if="=Drill"),
        "row_back": _attr(tr("Back row from the front edge"), "length", 0.0,
                          access="view", section=holes, show_if="=Drill",
                          formula=("=Row_Front + FLOOR((IF(Back_Panel, Back_Y, LenY)"
                                   " - 2*Row_Front)/Raster, 1)*Raster")),
        "hole_d": _attr(tr("Hole diameter"), "length", HOLE_D, access="textbox",
                        min=0.002, max=0.02, section=holes, show_if="=Drill"),
        "hole_depth": _attr(tr("Hole depth"), "length", HOLE_DEPTH, access="textbox",
                            min=0.002, max=0.05, section=holes, show_if="=Drill"),
        "edge_min": _attr(tr("Smallest distance first/last hole to bottom/top"),
                          "length", EDGE_MIN, access="textbox", min=0.01, max=0.2,
                          section=holes, show_if="=Drill"),
        "holes_k": _attr(tr("Holes per row"), "int", 0, access="view", min=0,
                         section=holes, show_if="=Drill",
                         formula="=MAX(0, FLOOR((In_H - 2*Edge_Min)/Raster, 1) + 1)"),
        # Derived, not shown
        "raster": _attr(tr("Hole raster"), "length", RASTER),
        "z_bottom": _attr("z_bottom", "length", formula="=IF(Plinth, Plinth_H, 0)"),
        "in_low": _attr("in_low", "length", formula="=Z_Bottom + Thickness"),
        "in_top": _attr("in_top", "length", formula="=LenZ - Thickness"),
        "in_h": _attr("in_h", "length", formula="=In_Top - In_Low"),
        # First hole: the row is centred between the panels, so the first and the
        # last hole are the same distance from the bottom and from the top panel.
        "z_first": _attr("z_first", "length", formula=(
            "=In_Low + (In_H - (MAX(Holes_K, 1) - 1)*Raster)/2")),
        "margin": _attr("margin", "length", formula="=Raster/2"),
        "groove_w": _attr("groove_w", "length", formula="=Back_Thick + 0.001"),
        "back_y": _attr("back_y", "length", formula="=LenY - Back_Inset - Groove_W"),
        "fields": _attr("fields", "int", formula="=Divs + 1"),
        "field_w": _attr("field_w", "length", formula=(
            "=(LenX - (Divs + 2)*Thickness)/(Divs + 1)")),
        "n_min": _attr("n_min", "int", formula=(
            "=MAX(0, CEILING((In_H - (Gap_Max - Margin))"
            "/MAX(Gap_Max - Margin + Thickness, 0.001), 1))")),
        "n_max": _attr("n_max", "int", formula=(
            "=FLOOR((In_H - (Gap_Min + Margin))/(Gap_Min + Margin + Thickness), 1)")),
    }
    nodes = {"": {"label": tr("Cabinet"), "attrs": root}}

    def part(name, label, attrs, **fields):
        nodes[name] = {"label": label, "attrs": attrs, **fields}

    part("side_left", tr("Left side"),
         _placement("=0", "=0", "=0", f"={S}", "=Parent!LenY", "=Parent!LenZ"),
         gen="board@1")
    part("side_right", tr("Right side"),
         _placement(f"=Parent!LenX - {S}", "=0", "=0", f"={S}", "=Parent!LenY",
                    "=Parent!LenZ"), gen="board@1")
    part("bottom", tr("Bottom"),
         _placement(f"={S}", "=0", "=Parent!Z_Bottom", inner_w, "=Parent!LenY",
                    f"={S}"), gen="board@1")
    part("top", tr("Top"),
         _placement(f"={S}", "=0", f"=Parent!LenZ - {S}", inner_w, "=Parent!LenY",
                    f"={S}"), gen="board@1")
    # The back panel sits in a groove in the sides, the bottom and the top; it goes
    # 1 mm less than the groove's depth into each so it is never tight.
    reach = "(Parent!Groove_D - 0.001)"
    part("back", tr("Back panel"),
         _placement(f"={S} - {reach}", "=Parent!Back_Y + (Parent!Groove_W - Parent!Back_Thick)/2",
                    f"=Parent!In_Low - {reach}", f"=Parent!LenX - 2*{S} + 2*{reach}",
                    "=Parent!Back_Thick", f"=Parent!In_H + 2*{reach}",
                    hidden="=NOT(Parent!Back_Panel)"))
    part("plinth", tr("Plinth panel"),
         _placement(f"={S}", "=Parent!Plinth_Set", "=0", inner_w, f"={S}",
                    "=Parent!Plinth_H", hidden="=NOT(Parent!Plinth)"))
    shelf = _placement(
        f"={S} + Field_Idx*(Parent!Field_W + {S}) + 0.001",
        "=0.02",
        ("=Parent!Z_First + MIN(MAX(Parent!Holes_K, 1) - 1, MAX(0, ROUND((Ideal"
         " - Parent!Support - Parent!Z_First)/Parent!Raster, 0)))*Parent!Raster"
         " + Parent!Support"),
        "=Parent!Field_W - 0.002", f"={shelf_depth} - 0.022", f"={S}",
        copies="=MAX(Parent!N*Parent!Fields - 1, 0)", hidden="=Parent!N < 1")
    # One copy per shelf and compartment: the level counts up, then the field.
    shelf["level"] = _attr("level", "int", formula="=FLOOR(Copy/Parent!Fields, 1)")
    shelf["field_idx"] = _attr("field_idx", "int", formula="=MOD(Copy, Parent!Fields)")
    shelf["ideal"] = _attr(tr("Ideal height"), "length", formula=(
        f"=Parent!In_Low + (Level + 1)*Parent!Gap + Level*{S}"))
    part("shelf", tr("Shelf"), shelf)
    part("divider", tr("Divider"),
         _placement(f"={S} + (Copy + 1)*Parent!Field_W + Copy*{S}", "=0",
                    "=Parent!In_Low", f"={S}", f"={shelf_depth}", "=Parent!In_H",
                    copies="=MAX(Parent!Divs - 1, 0)", hidden="=Parent!Divs < 1"),
         gen="board@1")
    rows = (("holes_lf", tr("Holes left, front"), "side_left", "Parent!Row_Front"),
            ("holes_lb", tr("Holes left, back"), "side_left", "Parent!Row_Back"),
            ("holes_rf", tr("Holes right, front"), "side_right", "Parent!Row_Front"),
            ("holes_rb", tr("Holes right, back"), "side_right", "Parent!Row_Back"))
    for name, label, side, row in rows:
        x = (f"={S} - Parent!Hole_Depth" if side == "side_left"
             else f"=Parent!LenX - {S} - 0.001")
        hidden = "=OR(NOT(Parent!Drill), Parent!Holes_K < 1"
        if row.endswith("Back"):
            hidden += ", Parent!Row_Back < Parent!Row_Front + 2*Parent!Hole_D"
        hidden += ")"
        part(name, label, _placement(
            x, f"={row} - Parent!Hole_D/2",
            "=Parent!Z_First + Copy*Parent!Raster - Parent!Hole_D/2",
            "=Parent!Hole_Depth + 0.001", "=Parent!Hole_D", "=Parent!Hole_D",
            copies="=MAX(Parent!Holes_K - 1, 0)", hidden=hidden), cut=side)
    # The grooves: cutters, each one cuts its board along the whole length (board@1).
    off = "=NOT(Parent!Back_Panel)"
    groove_y, groove_w = "=Parent!Back_Y", "=Parent!Groove_W"
    deep = "=Parent!Groove_D + 0.001"
    for name, label, target, x, z, lx, lz in (
            ("groove_l", tr("Groove left"), "side_left", f"={S} - Parent!Groove_D", "=-0.001",
             deep, "=Parent!LenZ + 0.002"),
            ("groove_r", tr("Groove right"), "side_right", f"=Parent!LenX - {S} - 0.001",
             "=-0.001", deep, "=Parent!LenZ + 0.002"),
            ("groove_b", tr("Groove bottom"), "bottom", f"={S} - 0.001",
             f"=Parent!Z_Bottom + {S} - Parent!Groove_D", f"=Parent!LenX - 2*{S} + 0.002",
             deep),
            ("groove_t", tr("Groove top"), "top", f"={S} - 0.001",
             f"=Parent!LenZ - {S} - 0.001", f"=Parent!LenX - 2*{S} + 0.002", deep)):
        part(name, label, _placement(x, groove_y, z, lx, groove_w, lz, hidden=off),
             cut=target)
    # Dividers are drilled right through, one row serves both of their faces (two
    # blind holes of the sides' depth would meet inside a 19 mm board).
    for name, label, row in (("holes_df", tr("Holes divider, front"), "Parent!Row_Front"),
                             ("holes_db", tr("Holes divider, back"), "Parent!Row_Back")):
        hidden = "=OR(NOT(Parent!Drill), Parent!Holes_K < 1, Parent!Divs < 1"
        if row.endswith("Back"):
            hidden += ", Parent!Row_Back < Parent!Row_Front + 2*Parent!Hole_D"
        hidden += ")"
        attrs = _placement(
            f"={S} + (Div_Idx + 1)*Parent!Field_W + Div_Idx*{S} - 0.001", f"={row} - Parent!Hole_D/2",
            "=Parent!Z_First + Hole_Idx*Parent!Raster - Parent!Hole_D/2",
            f"={S} + 0.002", "=Parent!Hole_D", "=Parent!Hole_D",
            copies="=MAX(Parent!Holes_K*Parent!Divs - 1, 0)", hidden=hidden)
        attrs["div_idx"] = _attr("div_idx", "int",
                                 formula="=FLOOR(Copy/MAX(Parent!Holes_K, 1), 1)")
        attrs["hole_idx"] = _attr("hole_idx", "int",
                                  formula="=MOD(Copy, MAX(Parent!Holes_K, 1))")
        part(name, label, attrs, cut="divider")
    return {"version": 1, "name": tr("Cabinet"), "nodes": nodes}


# ---------------------------------------------------------------- geometry

def _box_mesh(size):
    from core.mesh import Mesh
    sx, sy, sz = size
    v = [QVector3D(x, y, z) for z in (0.0, sz) for y in (0.0, sy) for x in (0.0, sx)]
    m = Mesh()
    for loop in ((0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3),
                 (0, 4, 6, 2), (1, 3, 7, 5)):
        m.add_face([v[i] for i in loop])
    return m


def _rod_mesh(length, diameter, segments=12):
    """A cylinder along +X from 0 to `length`, its box starting at the origin."""
    from core.mesh import Mesh
    r = diameter / 2
    ring = [(r + r * math.cos(2 * math.pi * k / segments),
             r + r * math.sin(2 * math.pi * k / segments)) for k in range(segments)]
    near = [QVector3D(0.0, y, z) for y, z in ring]
    far = [QVector3D(length, y, z) for y, z in ring]
    m = Mesh()
    m.add_face(list(reversed(near)))
    m.add_face(far)
    for k in range(segments):
        j = (k + 1) % segments
        m.add_face([near[k], near[j], far[j], far[k]])
    for e in m.edges:
        if abs(e.v0.position.x() - e.v1.position.x()) > 1e-9:
            e.soft = True
    return m


def _part(name, mesh, at, paint=None):
    from core.group import Group
    g = Group(mesh, name)
    g.xform = QMatrix4x4()
    g.xform.translate(*at)
    g.component = False
    if paint is not None:
        g.material = dict(paint)
    return g


def _parts():
    """(part name, group) at the starting size; the formulas place them."""
    W, D, H, S = WIDTH, DEPTH, HEIGHT, THICKNESS
    zb = 0.1
    inner = W - 2 * S
    in_h = H - zb - 2 * S
    k = max(math.floor(in_h / RASTER - 2 * EDGE_MIN / RASTER + 1e-9) + 1, 1)
    z_first = zb + S + (in_h - (k - 1) * RASTER) / 2
    rod_len = HOLE_DEPTH + 0.001
    rows = [("holes_lf", (S - HOLE_DEPTH, 0.037 - HOLE_D / 2)),
            ("holes_lb", (S - HOLE_DEPTH, 0.485 - HOLE_D / 2)),
            ("holes_rf", (W - S - 0.001, 0.037 - HOLE_D / 2)),
            ("holes_rb", (W - S - 0.001, 0.485 - HOLE_D / 2))]
    labels = {"side_left": tr("Left side"), "side_right": tr("Right side"),
              "bottom": tr("Bottom"), "top": tr("Top"), "back": tr("Back panel"),
              "plinth": tr("Plinth panel"), "shelf": tr("Shelf"),
              "groove_l": tr("Groove left"), "groove_r": tr("Groove right"),
              "groove_b": tr("Groove bottom"), "groove_t": tr("Groove top"),
              "divider": tr("Divider"), "holes_df": tr("Holes divider, front"),
              "holes_db": tr("Holes divider, back"),
              "holes_lf": tr("Holes left, front"), "holes_lb": tr("Holes left, back"),
              "holes_rf": tr("Holes right, front"), "holes_rb": tr("Holes right, back")}
    out = [
        ("side_left", _box_mesh((S, D, H)), (0, 0, 0), WOOD),
        ("side_right", _box_mesh((S, D, H)), (W - S, 0, 0), WOOD),
        ("bottom", _box_mesh((inner, D - BACK, S)), (S, 0, zb), WOOD),
        ("top", _box_mesh((inner, D - BACK, S)), (S, 0, H - S), WOOD),
        ("back", _box_mesh((inner, BACK, H - zb)), (S, D - BACK, zb), BACK_PAINT),
        ("plinth", _box_mesh((inner, S, zb)), (S, 0.04, 0), PLINTH_PAINT),
        ("shelf", _box_mesh((inner - 0.002, D - BACK - 0.022, S)), (S + 0.001, 0.02, 0.5),
         WOOD),
    ]
    for name in ("groove_l", "groove_r", "groove_b", "groove_t"):
        out.append((name, _box_mesh((0.01, 0.01, 0.01)), (0, 0, 0), None))
    # Dividers do not exist at the starting width; the formulas place them.
    out.append(("divider", _box_mesh((S, D - BACK, H - zb - 2 * S)), (W / 2, 0, zb + S),
                WOOD))
    for name, y in (("holes_df", 0.037 - HOLE_D / 2), ("holes_db", 0.485 - HOLE_D / 2)):
        out.append((name, _rod_mesh(S + 0.002, HOLE_D), (W / 2 - 0.001, y,
                                                         z_first - HOLE_D / 2), None))
    for name, (x, y) in rows:
        out.append((name, _rod_mesh(rod_len, HOLE_D), (x, y, z_first - HOLE_D / 2), None))
    return [(name, _part(labels[name], mesh, at, paint)) for name, mesh, at, paint in out]


def insert_cabinet(scene, at=(0.0, 0.0, 0.0), lang="en"):
    """Add a System 32 cabinet at `at` and lay it out, labelled in `lang` (en,
    de, es, fr). Mutates: run inside a DynamicCommand."""
    global _lang
    _lang = lang if lang in _LABELS else "en"
    from core.group import Group
    from core.mesh import Mesh

    from dynamic_components import binding

    parts = _parts()
    root = Group(Mesh(), tr("Cabinet"))
    root.adopt([g for _n, g in parts])
    root.component = True
    root.xform = QMatrix4x4()
    root.xform.translate(*at)
    scene.groups.append(root)
    binding.make_dynamic(scene, root, cabinet_spec(), names=[n for n, _g in parts])
    binding.apply(scene, root)
    return root


def main(argv) -> int:
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from core.scene import Scene
    from formats import igz

    args = [a for a in argv if not a.startswith("--")]
    lang = argv[argv.index("--lang") + 1] if "--lang" in argv else "en"
    if "--lang" in argv:
        args.remove(lang)
    out = Path(args[0] if args else Path(__file__).with_name("system32-cabinet.igz"))
    _app = QApplication.instance() or QApplication([])
    scene = Scene()
    insert_cabinet(scene, lang=lang)
    igz.save_scene(scene, out)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
