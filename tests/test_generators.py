"""generators: registry, mesh conversion, cache."""
import pytest

from core.solids import solid_report

from dynamic_components import generators, geometry
from dynamic_components.geometry import Box, GeometryError


def test_board_is_registered():
    assert generators.known("board@1") and "board@1" in generators.names()


def test_to_mesh_is_a_closed_solid_with_soft_walls_and_paint(qtapp):
    shape = geometry.board((0.019, 0.56, 1.0),
                           cuts=[Box((0.007, 0.1, 0.1), (0.02, 0.105, 0.105))])
    mesh = generators.to_mesh(shape, {"color": [0.8, 0.6, 0.4]})
    ok, vol = solid_report(mesh)
    assert ok and vol == pytest.approx(0.019 * 0.56 - 0.5 * 12 * 0.0025 ** 2 * 0.5 * 0.012,
                                       rel=1e-5)
    assert sum(e.soft for e in mesh.edges) == 12
    assert all(f.attrs.get("color") == (0.8, 0.6, 0.4) for f in mesh.faces)
    assert generators.fingerprint(mesh) == [len(mesh.faces), len(mesh.vertices)]


def test_register_rules():
    with pytest.raises(ValueError):
        generators.register("Board", lambda *a: None)
    with pytest.raises(ValueError):
        generators.register("board@1", lambda *a: None)
    with pytest.raises(ValueError):
        generators.register("thing@1", "not callable")


def test_build_fails_closed(monkeypatch):
    with pytest.raises(GeometryError) as info:
        generators.build("nothing@9", (1, 1, 1), (0, 0, 0), [], {})
    assert "nothing@9" in info.value.msg

    def broken(*_a):
        raise RuntimeError("boom")
    monkeypatch.setitem(generators._generators, "broken@1", broken)
    with pytest.raises(GeometryError) as info:
        generators.build("broken@1", (1, 1, 1), (0, 0, 0), [], {})
    assert "boom" in info.value.msg
    monkeypatch.setitem(generators._generators, "lazy@1", lambda *a: "no shape")
    with pytest.raises(GeometryError):
        generators.build("lazy@1", (1, 1, 1), (0, 0, 0), [], {})


def test_a_registered_generator_gets_size_origin_cuts_and_params(monkeypatch):
    seen = []

    def build(size, origin, cuts, params):
        seen.append((size, origin, cuts, params))
        return geometry.board(size, origin, cuts)
    monkeypatch.setitem(generators._generators, "probe@1", build)
    generators.build("probe@1", (1, 2, 3), (0, 0, 0), [], {"radius": 0.1})
    assert seen == [((1, 2, 3), (0, 0, 0), [], {"radius": 0.1})]


def test_clean_paint_keeps_only_safe_values():
    assert generators.clean_paint({"color": (1, 0.5, 0), "mat": "Oak", "texture": object(),
                                   "opacity": 0.5, "x": 1}) == {
        "color": [1.0, 0.5, 0.0], "mat": "Oak", "opacity": 0.5}
    assert generators.clean_paint(None) == {}


def test_cache_is_bounded(monkeypatch):
    monkeypatch.setattr(generators, "_cache", type(generators._cache)())
    monkeypatch.setattr(generators, "_CACHE_SIZE", 3)
    for i in range(5):
        generators.remember(f"k{i}", i)
    assert generators.cached("k0") is None and generators.cached("k4") == 4
    assert list(generators._cache) == ["k2", "k3", "k4"]
