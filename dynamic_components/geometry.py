"""Pure geometry for generated parts: a board with holes, pockets and grooves.

No Qt, no IngeTrazo: a :class:`Shape` is plain polygon data that the binding
turns into a mesh (``generators.to_mesh``). The board is built directly, without
a boolean library: every cut enters through one face (or goes through two
opposite ones), so each face is a rectangle with hole loops and each cut adds its
walls and, when blind, its bottom. Exact, fast and closed by construction.

A rectangular cut may also run along the whole length of the board from one
face: a groove. The board is then an extrusion of a
profile with slots; all grooves of a board run the same way from the same face.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .messages import MessageError, Msg, N_

Point = tuple
EPS = 1e-6          # 1 µm: closer than this counts as touching (placements
                    # pass through float32 matrices: ~2e-7 at 2 m)
MAX_CUTS = 2000
MAX_FACES = 200_000
_GRID = 0.05        # cell size for finding cuts that touch each other


class GeometryError(MessageError):
    """The whole shape failed (``.msg`` says why)."""


ROUND, RECT, AUTO = "round", "rect", "auto"


@dataclass(frozen=True)
class Box:
    """A cutter: axis-aligned box in the board's frame. ``kind`` says whether
    its cross-section is round or rectangular; ``auto`` = round when the two
    sides across the cut are equal."""
    lo: Point
    hi: Point
    kind: str = AUTO


@dataclass
class Shape:
    faces: list = field(default_factory=list)     # (outer, [holes])
    soft: list = field(default_factory=list)      # (a, b) edges drawn soft
    issues: list = field(default_factory=list)    # (cut index, Msg)


@dataclass
class _Cut:
    axis: int
    side: int                 # +1: enters through the face at hi[axis]; -1: at lo
    through: bool
    round_: bool
    u: tuple                  # (lo, hi) on the entry face's first axis
    v: tuple                  # (lo, hi) on its second axis
    bottom: float             # coordinate on `axis` where a blind cut ends
    clip: Box                 # the part of the cut inside the board


@dataclass
class _Slot:
    """A groove: along ``axis`` over the whole board, entering through the face
    at ``entry`` (+1: the high side), ``c`` the (lo, hi) across it."""
    axis: int
    entry_axis: int
    side: int
    c: tuple
    bottom: float             # coordinate on entry_axis where the groove ends
    clip: Box


def segments_for(diameter: float) -> int:
    """Segments of a round hole: fine enough to read round, few enough for
    hundreds of holes."""
    if diameter <= 0.010 + 1e-12:
        return 12
    if diameter <= 0.040 + 1e-12:
        return 24
    return 32


def _finite_point(p, what) -> tuple:
    try:
        values = tuple(float(c) for c in p)
    except (TypeError, ValueError):
        raise GeometryError(Msg("{what} is not a point", what=what)) from None
    if len(values) != 3 or not all(math.isfinite(c) for c in values):
        raise GeometryError(Msg("{what} is not a point", what=what))
    return values


def _basis(axis: int, side: int) -> tuple[int, int]:
    """Axes (u, v) of a face so that u × v is its outward normal side·e_axis."""
    a, b = (axis + 1) % 3, (axis + 2) % 3
    return (a, b) if side > 0 else (b, a)


def _point(axis: int, w: float, ua: int, u: float, va: int, v: float) -> tuple:
    p = [0.0, 0.0, 0.0]
    p[axis], p[ua], p[va] = w, u, v
    return tuple(p)


def _classify(cut: Box, lo, hi):
    """A usable cut, None when it misses the board, or a Msg why it cannot be
    made."""
    c_lo = _finite_point(cut.lo, N_("cut"))
    c_hi = _finite_point(cut.hi, N_("cut"))
    if any(c_hi[i] - c_lo[i] <= EPS for i in range(3)):
        return Msg("The cut has no volume")
    i_lo = tuple(max(c_lo[i], lo[i]) for i in range(3))
    i_hi = tuple(min(c_hi[i], hi[i]) for i in range(3))
    if any(i_hi[i] - i_lo[i] <= EPS for i in range(3)):
        return None
    crossing = []
    for i in range(3):
        below = c_lo[i] <= lo[i] + EPS
        above = c_hi[i] >= hi[i] - EPS
        if below or above:
            crossing.append((i, below, above))
    if not crossing:
        return Msg("The cut lies inside the board and reaches no face")
    if len(crossing) == 2:
        through = [c for c in crossing if c[1] and c[2]]
        entry = [c for c in crossing if not (c[1] and c[2])]
        if len(through) == 1 and len(entry) == 1:
            if cut.kind == ROUND:
                return Msg("A groove cannot be round")
            along, (entry_axis, below, above) = through[0][0], entry[0]
            across = 3 - along - entry_axis
            side = +1 if above else -1
            bottom = c_lo[entry_axis] if side > 0 else c_hi[entry_axis]
            return _Slot(along, entry_axis, side, (c_lo[across], c_hi[across]), bottom,
                         Box(i_lo, i_hi))
    if len(crossing) > 1:
        return Msg("The cut runs over an edge of the board; only holes, pockets "
                   "and grooves along a whole side can be made")
    axis, below, above = crossing[0]
    through = below and above
    side = +1 if above else -1
    ua, va = _basis(axis, side)
    wu, wv = c_hi[ua] - c_lo[ua], c_hi[va] - c_lo[va]
    equal = abs(wu - wv) <= max(2 * EPS, 1e-6 * max(wu, wv))
    if cut.kind == ROUND and not equal:
        return Msg("A round cut needs the same width in both directions across it")
    round_ = cut.kind == ROUND or (cut.kind == AUTO and equal)
    bottom = c_lo[axis] if side > 0 else c_hi[axis]
    return _Cut(axis, side, through, round_, (c_lo[ua], c_hi[ua]),
                (c_lo[va], c_hi[va]), bottom, Box(i_lo, i_hi))


def _touch(a: Box, b: Box) -> bool:
    return all(a.lo[i] <= b.hi[i] + EPS and b.lo[i] <= a.hi[i] + EPS for i in range(3))


def _cells(box: Box):
    ranges = [range(math.floor(box.lo[i] / _GRID), math.floor(box.hi[i] / _GRID) + 1)
              for i in range(3)]
    return [(x, y, z) for x in ranges[0] for y in ranges[1] for z in ranges[2]]


def _ring(cut: _Cut) -> list[tuple[float, float]]:
    """The cut's outline in its entry face's (u, v), counter-clockwise."""
    (u0, u1), (v0, v1) = cut.u, cut.v
    if not cut.round_:
        return [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
    cu, cv = (u0 + u1) / 2, (v0 + v1) / 2
    r = (u1 - u0) / 2
    n = segments_for(2 * r)
    return [(cu + r * math.cos(2 * math.pi * k / n), cv + r * math.sin(2 * math.pi * k / n))
            for k in range(n)]


def board(size, origin=(0.0, 0.0, 0.0), cuts=(), *, max_cuts=MAX_CUTS,
          max_faces=MAX_FACES) -> Shape:
    """A box [origin, origin + size] with the given cuts made (see module doc).
    Cuts that cannot be made are skipped and listed in ``issues``."""
    size = _finite_point(size, N_("size"))
    lo = _finite_point(origin, N_("origin"))
    if any(s <= EPS for s in size):
        raise GeometryError(Msg("The board has no volume"))
    hi = tuple(lo[i] + size[i] for i in range(3))
    cuts = list(cuts)
    if len(cuts) > max_cuts:
        raise GeometryError(Msg("Too many cuts in one board ({count}, limit {limit})",
                                count=len(cuts), limit=max_cuts))
    shape = Shape()
    accepted: list[_Cut] = []
    grid: dict = {}
    faces_needed = 6
    for index, raw in enumerate(cuts):
        if not isinstance(raw, Box):
            shape.issues.append((index, Msg("The cut is not a box")))
            continue
        cut = _classify(raw, lo, hi)
        if cut is None:
            shape.issues.append((index, Msg("The cut does not reach the board")))
            continue
        if isinstance(cut, Msg):
            shape.issues.append((index, cut))
            continue
        cells = _cells(cut.clip)
        if any(_touch(cut.clip, accepted[j].clip)
               for cell in cells for j in grid.get(cell, ())):
            shape.issues.append((index, Msg("The cut touches or overlaps another cut")))
            continue
        if isinstance(cut, _Slot):
            first = next((a for a in accepted if isinstance(a, _Slot)), None)
            if first is not None and (first.axis, first.entry_axis, first.side) != (
                    cut.axis, cut.entry_axis, cut.side):
                shape.issues.append((index, Msg("Grooves in one board must run the same "
                                                "way from the same face")))
                continue
            ring_size, extra = 3, 1
        else:
            ring_size, extra = len(_ring(cut)), (0 if cut.through else 1)
        faces_needed += ring_size + extra
        if faces_needed > max_faces:
            raise GeometryError(Msg("The board would get too many faces (limit {limit})",
                                    limit=max_faces))
        for cell in cells:
            grid.setdefault(cell, []).append(len(accepted))
        accepted.append(cut)
    _build(shape, lo, hi, accepted)
    return shape


def _facing(points: list, axis: int, sign: int) -> list:
    """The polygon wound so that its normal points along sign·e_axis."""
    a1, a2 = (axis + 1) % 3, (axis + 2) % 3
    total = 0.0
    for i, p in enumerate(points):
        q = points[(i + 1) % len(points)]
        total += (p[a1] - q[a1]) * (p[a2] + q[a2])
    return points if total * sign >= 0 else points[::-1]


def _build(shape: Shape, lo, hi, cuts: list) -> None:
    slots = sorted((c for c in cuts if isinstance(c, _Slot)), key=lambda c: c.c[0])
    cuts = [c for c in cuts if not isinstance(c, _Slot)]
    holes: dict[tuple[int, int], list] = {}
    for cut in cuts:
        ua, va = _basis(cut.axis, cut.side)
        ring = _ring(cut)
        entry = hi[cut.axis] if cut.side > 0 else lo[cut.axis]
        exit_ = lo[cut.axis] if cut.side > 0 else hi[cut.axis]
        end = exit_ if cut.through else cut.bottom
        top = [_point(cut.axis, entry, ua, u, va, v) for u, v in ring]
        low = [_point(cut.axis, end, ua, u, va, v) for u, v in ring]
        holes.setdefault((cut.axis, cut.side), []).append(top[::-1])
        if cut.through:
            holes.setdefault((cut.axis, -cut.side), []).append(list(low))
        else:
            shape.faces.append((list(low), []))
        n = len(ring)
        for k in range(n):
            j = (k + 1) % n
            shape.faces.append(([top[k], top[j], low[j], low[k]], []))
            if cut.round_:
                shape.soft.append((top[k], low[k]))
    if slots:
        _build_grooves(shape, lo, hi, slots, holes)
        return
    for axis in range(3):
        for side in (-1, +1):
            ua, va = _basis(axis, side)
            w = hi[axis] if side > 0 else lo[axis]
            outer = [_point(axis, w, ua, lo[ua], va, lo[va]),
                     _point(axis, w, ua, hi[ua], va, lo[va]),
                     _point(axis, w, ua, hi[ua], va, hi[va]),
                     _point(axis, w, ua, lo[ua], va, hi[va])]
            shape.faces.append((outer, holes.get((axis, side), [])))


def _build_grooves(shape: Shape, lo, hi, slots: list, holes: dict) -> None:
    """The faces of a board with grooves (``slots``, sorted across): the entry
    face is split into strips, the end faces get a notched outline, and every
    groove adds two walls and a floor."""
    A, B, side = slots[0].axis, slots[0].entry_axis, slots[0].side
    C = 3 - A - B
    entry = hi[B] if side > 0 else lo[B]
    other = lo[B] if side > 0 else hi[B]

    def at(a, b, c):
        p = [0.0, 0.0, 0.0]
        p[A], p[B], p[C] = a, b, c
        return tuple(p)

    # The two end faces: the profile (b, c) with a notch for every groove.
    profile = [(other, lo[C]), (entry, lo[C])]
    for slot in slots:
        c0, c1 = slot.c
        profile += [(entry, c0), (slot.bottom, c0), (slot.bottom, c1), (entry, c1)]
    profile += [(entry, hi[C]), (other, hi[C])]
    for end in (-1, +1):
        a = hi[A] if end > 0 else lo[A]
        loop = _facing([at(a, b, c) for b, c in profile], A, end)
        shape.faces.append((loop, holes.get((A, end), [])))
    # The face opposite the entry and the two across the grooves are plain.
    for axis, sd in ((B, -side), (C, -1), (C, +1)):
        ua, va = _basis(axis, sd)
        w = hi[axis] if sd > 0 else lo[axis]
        shape.faces.append(([_point(axis, w, ua, lo[ua], va, lo[va]),
                             _point(axis, w, ua, hi[ua], va, lo[va]),
                             _point(axis, w, ua, hi[ua], va, hi[va]),
                             _point(axis, w, ua, lo[ua], va, hi[va])],
                            holes.get((axis, sd), [])))
    # The entry face, in strips between the grooves.
    edges = [lo[C]] + [x for slot in slots for x in slot.c] + [hi[C]]
    strips = [(edges[i], edges[i + 1]) for i in range(0, len(edges), 2)]
    entry_holes = holes.get((B, side), [])
    for c0, c1 in strips:
        mine = [h for h in entry_holes if c0 - EPS <= sum(p[C] for p in h) / len(h) <= c1 + EPS]
        shape.faces.append((_facing([at(lo[A], entry, c0), at(hi[A], entry, c0),
                                     at(hi[A], entry, c1), at(lo[A], entry, c1)], B, side),
                            mine))
    for slot in slots:
        c0, c1 = slot.c
        floor = [at(lo[A], slot.bottom, c0), at(hi[A], slot.bottom, c0),
                 at(hi[A], slot.bottom, c1), at(lo[A], slot.bottom, c1)]
        shape.faces.append((_facing(floor, B, side), []))
        for c, sign in ((c0, +1), (c1, -1)):
            wall = [at(lo[A], entry, c), at(hi[A], entry, c),
                    at(hi[A], slot.bottom, c), at(lo[A], slot.bottom, c)]
            shape.faces.append((_facing(wall, C, sign), []))
