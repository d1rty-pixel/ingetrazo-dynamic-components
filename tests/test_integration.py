"""End to end with the real modules: binding, evaluator, UI, host History and .igz."""
from types import SimpleNamespace

import pytest
from PySide6.QtGui import QMatrix4x4, QVector3D as V

from core.group import Group, copy_group
from core.history import History
from core.mesh import Mesh
from core.scene import Scene

from dynamic_components import binding

KEY = binding.KEY


def _box(lx, ly, lz):
    m = Mesh()
    c = [V(x, y, z) for z in (0, lz) for y in (0, ly) for x in (0, lx)]
    for idx in ((0, 1, 3, 2), (4, 5, 7, 6), (0, 1, 5, 4),
                (2, 3, 7, 6), (0, 2, 6, 4), (1, 3, 7, 5)):
        m.add_face([c[i] for i in idx])
    return m


def _part(name, size, at):
    g = Group(_box(*size), name)
    g.xform = QMatrix4x4()
    g.xform.translate(*at)
    g.component = False
    return g


SPEC = {"version": 1, "name": "Shelf", "nodes": {
    "": {"attrs": {
        "width": {"label": "Width", "type": "length", "value": 1.0,
                  "access": "textbox", "min": 0.5, "max": 3.0},
        "boards": {"label": "Boards", "type": "int", "value": 3,
                   "access": "textbox", "min": 1, "max": 20}}},
    "board": {"attrs": {
        "lenx": {"type": "length", "value": 1.0, "formula": "=Parent!Width"},
        "copies": {"type": "int", "value": 0, "formula": "=Parent!Boards - 1"},
        "z": {"type": "length", "value": 0.0, "formula": "=COPY * 0.4"}}},
    "side": {"attrs": {
        "x": {"type": "length", "value": 1.0, "formula": "=Parent!Width"}}}}}


@pytest.fixture
def shelf(qtapp):
    scene = Scene()
    root = Group(Mesh(), "Shelf")
    root.adopt([_part("Board", (1.0, 0.3, 0.02), (0, 0, 0)),
                _part("Side", (0.02, 0.3, 1.0), (1.0, 0, 0))])
    scene.groups.append(root)
    viewport = SimpleNamespace(scene=scene, history=History(scene),
                               notify_scene_changed=lambda: None)
    app = SimpleNamespace(scene=scene, viewport=viewport, key=KEY, window=None)
    return app, root


def _boards(root):
    return [c for c in root.children if c.ext[KEY]["part"] == "board"]


def _make(app, root, spec=SPEC):
    binding.run(app.viewport, lambda s: binding.make_dynamic(s, root, spec),
                [root], "Make dynamic")
    binding.run(app.viewport, lambda s: binding.apply(s, root), [root], "Apply")


def test_make_dynamic_apply_and_undo(shelf):
    app, root = shelf
    _make(app, root)
    assert len(_boards(root)) == 3
    assert [round(b.xform.data()[14], 6) for b in _boards(root)] == [0.0, 0.4, 0.8]
    hist = app.viewport.history
    hist.undo()
    assert len(_boards(root)) == 1
    hist.undo()
    assert not binding.is_dynamic(root) and len(root.children) == 2
    assert all(not (c.ext or {}).get(KEY) for c in root.children)
    hist.redo()
    hist.redo()
    assert len(_boards(root)) == 3


def test_options_dialog_drives_parts(shelf):
    from dynamic_components.ui.options import OptionsDialog
    app, root = shelf
    _make(app, root)
    dialog = OptionsDialog(app, root)
    dialog._rows[("", "width")][0].__self__.setValue(2.0)
    dialog._rows[("", "boards")][0].__self__.setValue(5)
    dialog.apply()
    boards = _boards(root)
    assert len(boards) == 5
    assert all(b.xform.data()[0] == pytest.approx(2.0) for b in boards)
    side = next(c for c in root.children if c.ext[KEY]["part"] == "side")
    assert side.xform.data()[12] == pytest.approx(2.0)
    app.viewport.history.undo()
    assert len(_boards(root)) == 3


def test_options_dialog_clamps_to_max(shelf):
    app, root = shelf
    _make(app, root)
    binding.run(app.viewport,
                lambda s: binding.set_values(s, root, {"": {"boards": 500}}),
                [root], "Options")
    assert len(_boards(root)) == 20


def test_attributes_panel_edits_definition_for_all_copies(shelf):
    from dynamic_components.ui.attributes import AttributesPanel
    app, root = shelf
    _make(app, root)
    other = copy_group(root, V(5, 0, 0))
    app.scene.groups.append(other)
    app.scene.selection.add(root)
    panel = AttributesPanel(app)
    board = next(panel.tree.topLevelItem(i) for i in range(panel.tree.topLevelItemCount())
                 if panel.tree.topLevelItem(i).data(0, 0x0100) == "board"
                 or panel.tree.topLevelItem(i).text(0).lower() == "board")
    panel.tree.setCurrentItem(board)
    panel.name_edit.setText("leny")
    panel.type_combo.setCurrentText("length")
    panel.value_edit.setText("0.3")
    panel.formula_edit.setText("=Parent!Width / 2")
    panel.set_attribute()
    assert panel.status.text() == ""
    panel.apply()
    assert panel.status.text() == ""
    for inst in (root, other):
        for b in _boards(inst):
            # leny = 0.5 m over a 0.3 m rest depth
            assert b.xform.column(1).toVector3D().length() == pytest.approx(0.5 / 0.3)


def test_bad_formula_fails_closed(shelf):
    app, root = shelf
    spec = {**SPEC, "nodes": {**SPEC["nodes"], "side": {"attrs": {
        "x": {"type": "length", "value": 1.0, "formula": "=Parent!Width / 0"}}}}}
    _make(app, root, spec)
    side = next(c for c in root.children if c.ext[KEY]["part"] == "side")
    assert side.xform.data()[12] == pytest.approx(1.0)
    result = binding.apply(app.scene, root)
    assert ("side", "x") in result.errors


def test_scale_is_absorbed_into_lenx(shelf):
    app, root = shelf
    _make(app, root, {**SPEC, "nodes": {**SPEC["nodes"], "": {"attrs": {
        **SPEC["nodes"][""]["attrs"],
        "width": {"label": "Width", "type": "length", "value": 1.0,
                  "formula": "=LenX", "access": "view"}}}}})
    root.xform.scale(2.0, 1.0, 1.0)
    assert binding.absorbable_axes(app.scene, root) == [0]
    binding.run(app.viewport, lambda s: binding.absorb_scale(s, root), [root], "Scale")
    assert root.xform.column(0).toVector3D().length() == pytest.approx(1.0)
    # Rest width 1.02 m: the board plus the side standing at x = 1.0.
    assert root.ext[KEY]["set"][""]["lenx"] == pytest.approx(2.04)
    assert all(b.xform.data()[0] == pytest.approx(2.04) for b in _boards(root))
    assert binding.absorbable_axes(app.scene, root) == []


def test_igz_round_trip_keeps_definition(shelf, tmp_path):
    from formats import igz
    app, root = shelf
    _make(app, root)
    path = tmp_path / "shelf.igz"
    igz.save_scene(app.scene, path)
    opened = Scene()
    igz.load_into(opened, path)
    loaded = next(g for g in opened.groups if binding.is_dynamic(g))
    assert binding.definition(opened, loaded)["name"] == "Shelf"
    assert len(_boards(loaded)) == 3
    binding.set_values(opened, loaded, {"": {"boards": 4}})
    assert len(_boards(loaded)) == 4


@pytest.mark.parametrize("defs,record", [
    ({"d": "not a spec"}, {"def": "d"}),
    ({"d": {"version": 1, "name": "X", "nodes": {"": {"attrs": {
        "w": {"type": "length", "value": "__import__('os')"}}}}}}, {"def": "d"}),
    ({"d": {"version": 1, "name": "X", "nodes": {"": {"attrs": {}}}}},
     {"def": "d", "set": "garbage", "last": ["garbage"]}),
    ({}, {"def": "missing"}),
])
def test_hostile_document_fails_closed(shelf, defs, record):
    app, root = shelf
    app.scene.plugin_data[KEY] = {"version": 1, "defs": defs}
    root.ext = {KEY: record}
    before = [QMatrix4x4(c.xform) for c in root.children]
    try:
        binding.run(app.viewport, lambda s: binding.apply(s, root), [root], "Apply")
    except (ValueError, TypeError, KeyError) as exc:
        assert str(exc)
    assert [QMatrix4x4(c.xform) for c in root.children] == before
