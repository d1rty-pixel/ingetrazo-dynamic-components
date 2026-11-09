import copy

import pytest
from PySide6.QtGui import QMatrix4x4, QVector3D as V

from core.group import Group, copy_group
from core.history import History
from core.materials import Material
from core.mesh import Mesh
from core.scene import Scene

pytest.importorskip("dynamic_components.spec")
pytest.importorskip("dynamic_components.formula")

from dynamic_components import binding  # noqa: E402
from dynamic_components import evaluate as ev  # noqa: E402

KEY = binding.KEY


def _box_mesh(lx, ly, lz):
    m = Mesh()
    c = [V(x, y, z) for z in (0, lz) for y in (0, ly) for x in (0, lx)]
    for idx in ((0, 1, 3, 2), (4, 5, 7, 6), (0, 1, 5, 4),
                (2, 3, 7, 6), (0, 2, 6, 4), (1, 3, 7, 5)):
        m.add_face([c[i] for i in idx])
    return m


def _xf(tx=0.0, ty=0.0, tz=0.0):
    m = QMatrix4x4()
    m.translate(tx, ty, tz)
    return m


def _part(name, size, at=(0, 0, 0)):
    g = Group(_box_mesh(*size), name)
    g.xform = _xf(*at)
    g.component = False
    return g


@pytest.fixture
def door(qtapp):
    scene = Scene()
    root = Group(Mesh(), "Door")
    root.adopt([_part("Leaf", (0.9, 0.05, 2.0), (0.05, 0, 0)),
                _part("Knob", (0.1, 0.1, 0.1), (0.8, 0, 1.0))])
    scene.groups.append(root)
    return scene, root


def _res(**placements):
    return ev.Result(values={}, placements=placements, errors={})


def _pl(copy_=0, **kw):
    return ev.Placement(copy=copy_, **kw)


def _data(g):
    return [round(v, 5) for v in g.xform.data()]


def _spec_formula(src):
    return {"version": 1, "name": "Door", "nodes": {
        "": {"attrs": {}},
        "leaf": {"attrs": {"lenx": {"type": "length", "value": 0.9,
                                    "formula": src}}}}}


def test_make_dynamic_records_parts_and_rest(door):
    scene, root = door
    def_id = binding.make_dynamic(scene, root)
    assert binding.is_dynamic(root)
    assert root.ext[KEY]["def"] == def_id
    spec = binding.definition(scene, root)
    assert set(spec["nodes"]) == {"", "leaf", "knob"}
    assert root.children[0].ext[KEY] == {"part": "leaf"}
    assert spec["nodes"]["leaf"]["rest"]["size"] == pytest.approx([0.9, 0.05, 2.0])
    assert spec["nodes"]["leaf"]["rest"]["xform"][12] == pytest.approx(0.05)
    assert spec["nodes"][""]["rest"]["size"] == pytest.approx([0.9, 0.1, 2.0])
    assert binding.registry(scene)[def_id]["name"] == "Door"
    assert binding.instances_of(scene, def_id) == [root]


def test_part_names_are_unique_lowercase(qtapp):
    scene = Scene()
    root = Group(Mesh(), "R")
    root.adopt([_part("Leaf", (1, 1, 1)), _part("LEAF", (1, 1, 1))])
    scene.groups.append(root)
    binding.make_dynamic(scene, root)
    assert [c.ext[KEY]["part"] for c in root.children] == ["leaf", "leaf_2"]


def test_part_names_are_usable_in_formulas(qtapp):
    scene = Scene()
    root = Group(Mesh(), "R")
    root.adopt([_part("Group 1", (1, 1, 1)), _part("2 Böden", (1, 1, 1)),
                _part("  ", (1, 1, 1)), _part("Parent", (1, 1, 1))])
    scene.groups.append(root)
    binding.make_dynamic(scene, root)
    assert [c.ext[KEY]["part"] for c in root.children] == [
        "group_1", "part_2_böden", "part", "parent_part"]


def test_make_dynamic_rejects_plain_group_and_twice(door):
    scene, root = door
    with pytest.raises(ValueError):
        binding.make_dynamic(scene, Group(Mesh(), "x"))
    binding.make_dynamic(scene, root)
    with pytest.raises(ValueError):
        binding.make_dynamic(scene, root)


def test_xform_translation_only(door):
    scene, root = door
    binding.make_dynamic(scene, root)
    binding._write(scene, root, _res(leaf=[_pl(x=0.3, z=0.5)]))
    leaf = root.children[0]
    d = leaf.xform.data()
    assert (d[12], d[13], d[14]) == pytest.approx((0.3, 0.0, 0.5))
    assert d[0] == pytest.approx(1.0)


def test_xform_scale_only(door):
    scene, root = door
    binding.make_dynamic(scene, root)
    binding._write(scene, root, _res(leaf=[_pl(lenx=1.8, leny=None, lenz=1.0)]))
    d = root.children[0].xform.data()
    assert (d[0], d[5], d[10]) == pytest.approx((2.0, 1.0, 0.5))
    assert d[12] == pytest.approx(0.05)


def test_xform_rotation_keeps_scale(door):
    scene, root = door
    binding.make_dynamic(scene, root)
    binding._write(scene, root, _res(leaf=[_pl(rotz=90.0)]))
    d = root.children[0].xform.data()
    assert (d[0], d[1]) == pytest.approx((0.0, 1.0), abs=1e-6)
    assert (d[4], d[5]) == pytest.approx((-1.0, 0.0), abs=1e-6)
    assert d[12] == pytest.approx(0.05)


def test_zero_size_axis_is_not_scaled(qtapp):
    scene = Scene()
    root = Group(Mesh(), "R")
    flat = Group(Mesh(), "Flat")
    flat.mesh.add_face([V(0, 0, 0), V(1, 0, 0), V(1, 1, 0), V(0, 1, 0)])
    flat.xform = QMatrix4x4()
    root.adopt([flat])
    scene.groups.append(root)
    binding.make_dynamic(scene, root)
    binding._write(scene, root, _res(flat=[_pl(lenz=5.0)]))
    assert root.children[0].xform.data()[10] == pytest.approx(1.0)


def test_copies_grow_and_shrink_and_share_mesh(door):
    scene, root = door
    binding.make_dynamic(scene, root)
    knob = root.children[1]
    binding._write(scene, root, _res(knob=[_pl(), _pl(1, x=0.1), _pl(2, x=0.2)]))
    names = [c.ext[KEY] for c in root.children]
    assert names == [{"part": "leaf"}, {"part": "knob"},
                     {"part": "knob", "copy": 1}, {"part": "knob", "copy": 2}]
    c1 = root.children[2]
    assert c1.mesh is knob.mesh and c1.uid != knob.uid
    assert c1.xform.data()[12] == pytest.approx(0.1)
    binding._write(scene, root, _res(knob=[_pl(), _pl(1, x=0.4)]))
    assert root.children[2] is c1                 # updated in place
    assert c1.xform.data()[12] == pytest.approx(0.4)
    assert len(root.children) == 3
    binding._write(scene, root, _res(knob=[_pl()]))
    assert len(root.children) == 2


def test_hidden_and_material(door):
    scene, root = door
    scene.materials["Oak"] = Material("Oak", color=(0.6, 0.4, 0.2))
    binding.make_dynamic(scene, root)
    binding._write(scene, root, _res(
        leaf=[_pl(hidden=True, material="oak")],
        knob=[_pl(hidden=False, material="Nope")]))
    leaf, knob = root.children
    assert leaf.hidden is True
    assert leaf.material["mat"] == "Oak" and leaf.material["color"] == (0.6, 0.4, 0.2)
    assert knob.hidden is False and knob.material is None


def test_undo_redo_restores_exactly(door):
    scene, root = door
    hist = History(scene)
    before_children = list(root.children)

    def mutate(sc):
        binding.make_dynamic(sc, root)
        binding._write(sc, root, _res(
            knob=[_pl(), _pl(1, x=0.1)], leaf=[_pl(lenx=1.8, hidden=True)]))

    hist.execute(binding.DynamicCommand(mutate, [root]))
    assert hist.last_error is None
    assert len(root.children) == 3 and binding.is_dynamic(root)
    after_xform = _data(root.children[0])
    after_children = list(root.children)

    hist.undo()
    assert root.children == before_children and root.ext is None
    assert KEY not in scene.plugin_data
    assert _data(root.children[0])[0] == 1.0 and not root.children[0].hidden
    assert root.children[0].ext is None

    hist.redo()
    assert root.children == after_children
    assert _data(root.children[0]) == after_xform
    assert root.children[0].hidden
    assert binding.is_dynamic(root) and KEY in scene.plugin_data


def test_command_rolls_back_and_reraises(door):
    scene, root = door
    cmd = binding.DynamicCommand(
        lambda sc: (binding.make_dynamic(sc, root), 1 / 0), [root])
    with pytest.raises(ZeroDivisionError):
        cmd.do(scene)
    assert root.ext is None and root.children[0].ext is None
    assert KEY not in scene.plugin_data


@pytest.fixture
def fake_eval(monkeypatch):
    monkeypatch.setattr(binding._evaluate, "evaluate",
                        lambda spec, ov, last=None, **kw: _res())


def _scaled(root, sx, sy, sz):
    m = QMatrix4x4(root.xform)
    m.scale(sx, sy, sz)
    root.xform = m


def test_absorb_scale_only_used_axis(door, fake_eval):
    scene, root = door
    binding.make_dynamic(scene, root, _spec_formula("=Parent!LenX - 0.1"))
    root.xform = _xf(1, 2, 3)
    _scaled(root, 2.0, 3.0, 1.0)
    assert binding.absorb_scale(scene, root) is True
    d = root.xform.data()
    assert (d[0], d[5], d[10]) == pytest.approx((1.0, 3.0, 1.0))
    assert (d[12], d[13], d[14]) == pytest.approx((1, 2, 3))
    assert root.ext[KEY]["set"][""]["lenx"] == pytest.approx(0.9 * 2.0)
    assert binding.absorb_scale(scene, root) is False


def test_absorb_scale_accumulates_override_and_keeps_rotation(door, fake_eval):
    scene, root = door
    binding.make_dynamic(scene, root, _spec_formula("=Parent!LenX"))
    root.ext[KEY]["set"] = {"": {"lenx": 1.5}}
    r = QMatrix4x4()
    r.rotate(90, 0, 0, 1)
    r.scale(2.0, 1.0, 1.0)
    root.xform = r
    assert binding.absorb_scale(scene, root)
    assert root.ext[KEY]["set"][""]["lenx"] == pytest.approx(3.0)
    d = root.xform.data()
    assert (d[0], d[1]) == pytest.approx((0.0, 1.0), abs=1e-6)


def test_absorb_scale_ignores_unused_axes(door, fake_eval):
    scene, root = door
    binding.make_dynamic(scene, root, _spec_formula("=Parent!LenX"))
    _scaled(root, 1.0, 2.0, 2.0)
    assert binding.absorb_scale(scene, root) is False
    assert root.xform.data()[5] == pytest.approx(2.0)


def test_bake_removes_records_but_keeps_geometry(door):
    scene, root = door
    binding.make_dynamic(scene, root)
    binding._write(scene, root, _res(knob=[_pl(), _pl(1, x=0.1)]))
    n = len(root.children)
    xf = _data(root.children[2])
    binding.bake(scene, root)
    assert not binding.is_dynamic(root) and root.ext is None
    assert all(c.ext is None for c in root.children)
    assert len(root.children) == n and _data(root.children[2]) == xf


def test_copy_group_keeps_def_id(door):
    scene, root = door
    def_id = binding.make_dynamic(scene, root)
    clone = copy_group(root, V(3, 0, 0))
    scene.groups.append(clone)
    assert clone.ext[KEY]["def"] == def_id
    assert clone.children[0].ext[KEY] == {"part": "leaf"}
    assert set(binding.instances_of(scene, def_id)) == {root, clone}


def test_set_values_and_definition_end_to_end(door):
    scene, root = door
    spec = {"version": 1, "name": "Door", "nodes": {
        "": {"attrs": {"width": {"type": "length", "value": 0.9,
                                 "access": "textbox"}}},
        "leaf": {"attrs": {"lenx": {"type": "length", "value": 0.9,
                                    "formula": "=Parent!Width"}}}}}
    binding.make_dynamic(scene, root, spec)
    try:
        res = binding.set_values(scene, root, {"": {"width": "1.8"}})
    except NotImplementedError:
        pytest.skip("evaluate.evaluate not implemented yet")
    assert root.ext[KEY]["set"][""]["width"] == 1.8
    assert res.values[""]["width"] == pytest.approx(1.8)
    assert root.children[0].xform.data()[0] == pytest.approx(2.0)
    assert root.ext[KEY]["last"][""]["width"] == pytest.approx(1.8)
    other = copy_group(root)
    scene.groups.append(other)
    new = binding.definition(scene, root)
    new["nodes"]["leaf"]["attrs"]["lenx"]["formula"] = "=Parent!Width * 2"
    binding.set_definition(scene, root.ext[KEY]["def"], new)
    # The copy inherited width 1.8, so leaf = 3.6 m over a 0.9 m rest size.
    assert other.children[0].xform.data()[0] == pytest.approx(4.0)
    assert root.children[0].xform.data()[0] == pytest.approx(4.0)


def test_settle_pulls_back_a_pushed_down_matrix_only(door):
    scene, root = door
    binding.make_dynamic(scene, root)
    binding.apply(scene, root)
    root.xform.translate(3.0, 1.0, 0.0)          # a plain move: nothing to settle
    assert binding.settle(scene, root) is False
    moved = QMatrix4x4(root.xform)
    for child in root.children:                   # what entering the group does
        child.xform = moved * child.xform
    root.xform = QMatrix4x4()
    assert binding.settle(scene, root) is True
    assert list(root.xform.data()) == pytest.approx(list(moved.data()))
    assert binding.settle(scene, root) is False
