"""Generators: named code that builds a part's mesh at its final size.

A document only names a generator (``"board@1"``) and supplies values; the code
lives here or in another installed extension (``register``). Python stored in a
document is never run.
"""
from __future__ import annotations

import re
from collections import OrderedDict

from . import geometry
from .messages import Msg, text_of

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*@[0-9]+$")
_CACHE_SIZE = 256
_PAINT_KEYS = ("color", "mat", "opacity")

_generators: dict = {}
_cache: OrderedDict = OrderedDict()


def register(name: str, build) -> None:
    """Add a generator: ``build(size, origin, cuts, params) -> geometry.Shape``."""
    if not isinstance(name, str) or not _NAME_RE.match(name):
        raise ValueError(f"Generator name {name!r} is not of the form kind@version")
    if name in _generators:
        raise ValueError(f"Generator {name!r} is registered already")
    if not callable(build):
        raise ValueError("build must be callable")
    _generators[name] = build


def known(name: str) -> bool:
    return name in _generators


def names() -> list[str]:
    return sorted(_generators)


def build(name, size, origin, cuts, params):
    """The generator's shape; GeometryError for an unknown name or anything
    the generator raised (fail closed: the caller keeps the old mesh)."""
    fn = _generators.get(name)
    if fn is None:
        raise geometry.GeometryError(Msg("Unknown generator {name}", name=repr(name)))
    try:
        shape = fn(size, origin, cuts, params)
    except geometry.GeometryError:
        raise
    except Exception as exc:  # noqa: BLE001 - extension code: fail closed
        raise geometry.GeometryError(Msg("Generator {name} failed: {error}",
                                         name=name, error=text_of(exc))) from None
    if not isinstance(shape, geometry.Shape):
        raise geometry.GeometryError(Msg("Generator {name} returned no shape", name=name))
    return shape


def clean_paint(attrs) -> dict:
    """The paint of a face that generated faces may carry (JSON-safe)."""
    paint = {}
    for key in _PAINT_KEYS:
        value = (attrs or {}).get(key)
        if isinstance(value, (list, tuple)) and all(isinstance(c, (int, float)) for c in value):
            paint[key] = [float(c) for c in value]
        elif isinstance(value, (str, int, float)) and not isinstance(value, bool):
            paint[key] = value
    return paint


def to_mesh(shape, paint=None):
    """An IngeTrazo mesh from a shape: faces with holes, round walls soft."""
    from PySide6.QtGui import QVector3D
    from core.mesh import Mesh

    mesh = Mesh()
    face_attrs = {}
    for key, value in (paint or {}).items():
        face_attrs[key] = tuple(value) if isinstance(value, list) else value
    for outer, holes in shape.faces:
        face = mesh.add_face([QVector3D(*p) for p in outer],
                             [[QVector3D(*p) for p in h] for h in holes] or None)
        if face_attrs:
            face.attrs.update(face_attrs)
    if shape.soft:
        by_ends = {frozenset((id(e.v0), id(e.v1))): e for e in mesh.edges}
        for a, b in shape.soft:
            va, vb = mesh.vertex_at(QVector3D(*a)), mesh.vertex_at(QVector3D(*b))
            edge = by_ends.get(frozenset((id(va), id(vb)))) if va and vb else None
            if edge is not None:
                edge.soft = True
    return mesh


def fingerprint(mesh) -> list[int]:
    return [len(mesh.faces), len(mesh.vertices)]


def cached(key):
    mesh = _cache.get(key)
    if mesh is not None:
        _cache.move_to_end(key)
    return mesh


def remember(key, mesh) -> None:
    _cache[key] = mesh
    _cache.move_to_end(key)
    while len(_cache) > _CACHE_SIZE:
        _cache.popitem(last=False)


def _board(size, origin, cuts, params):
    return geometry.board(size, origin, cuts)


register("board@1", _board)
