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


def _panel(app, root):
    from dynamic_components.ui.panel import DynamicPanel
    app.scene.selection.clear()
    app.scene.selection.add(root)
    return DynamicPanel(app)


def test_options_in_the_panel_drive_parts_one_undo_step_each(shelf):
    app, root = shelf
    _make(app, root)
    panel = _panel(app, root)
    rows = panel.options._rows
    lengths = panel.options._lengths
    hist = app.viewport.history
    steps = len(hist.undo_stack)
    rows[("", "width")].editor.widget.setValue(lengths.show(2.0))
    rows[("", "boards")].editor.widget.setValue(5)
    assert len(hist.undo_stack) == steps + 2
    boards = _boards(root)
    assert len(boards) == 5
    assert all(b.xform.data()[0] == pytest.approx(2.0) for b in boards)
    side = next(c for c in root.children if c.ext[KEY]["part"] == "side")
    assert side.xform.data()[12] == pytest.approx(2.0)
    hist.undo()
    assert len(_boards(root)) == 3


def test_reset_button_drops_the_instance_value(shelf):
    app, root = shelf
    _make(app, root)
    panel = _panel(app, root)
    row = panel.options._rows[("", "boards")]
    assert row.reset.isHidden()
    row.editor.widget.setValue(6)
    panel.refresh()
    assert not row.reset.isHidden()
    row.reset.click()
    assert "boards" not in root.ext[KEY]["set"].get("", {})
    assert len(_boards(root)) == 3
    panel.refresh()
    assert row.editor.widget.value() == 3 and row.reset.isHidden()


def test_panel_refresh_updates_in_place(shelf):
    app, root = shelf
    _make(app, root)
    panel = _panel(app, root)
    widget = panel.options._rows[("", "width")].editor.widget
    binding.run(app.viewport,
                lambda s: binding.set_values(s, root, {"": {"width": 1.5}}),
                [root], "Options")
    panel.refresh()
    assert panel.options._rows[("", "width")].editor.widget is widget
    assert panel.options._lengths.si(widget.value()) == pytest.approx(1.5)


def test_panel_bake_and_make_dynamic(shelf):
    app, root = shelf
    panel = _panel(app, root)
    assert not panel.placeholder.isHidden() and not panel.make_button.isHidden()
    panel.make_dynamic()
    assert binding.is_dynamic(root)
    assert panel.title.text() == "Shelf" and not panel.bake_button.isHidden()
    panel.bake()
    assert not binding.is_dynamic(root)
    assert panel.bake_button.isHidden()


def test_options_dialog_clamps_to_max(shelf):
    app, root = shelf
    _make(app, root)
    binding.run(app.viewport,
                lambda s: binding.set_values(s, root, {"": {"boards": 500}}),
                [root], "Options")
    assert len(_boards(root)) == 20


def test_attributes_editor_edits_definition_for_all_copies(shelf):
    app, root = shelf
    _make(app, root)
    other = copy_group(root, V(5, 0, 0))
    app.scene.groups.append(other)
    panel = _panel(app, root)
    editor = panel.attributes
    editor.add_attribute("board", "leny")
    card = editor._card
    assert card is not None and (card.node, card.name) == ("board", "leny")
    assert "Parent!width" in card._words() and "IF(" in card._words()
    steps = len(app.viewport.history.undo_stack)
    card.formula_edit.setText("=Parent!Width / 2")
    card._formula_typed(card.formula_edit.text())
    assert card.preview.text().startswith("✓")
    assert len(app.viewport.history.undo_stack) == steps   # typing: preview only
    card._formula_done()                                    # the field is left
    assert len(app.viewport.history.undo_stack) == steps + 1
    assert editor.status.text() == "" and not editor.dirty
    for inst in (root, other):
        for b in _boards(inst):
            # leny = 0.5 m over a 0.3 m rest depth
            assert b.xform.column(1).toVector3D().length() == pytest.approx(0.5 / 0.3)


def test_attributes_editor_custom_attribute_and_choices(shelf):
    app, root = shelf
    _make(app, root)
    panel = _panel(app, root)
    editor = panel.attributes
    editor.add_attribute("", None)
    card = editor._card
    card.label_edit.setText("Plattenstärke")
    card._label_typed("Plattenstärke")
    card._label_done()
    card = editor._card
    assert card.name == "plattenstaerke"
    card.access_combo.setCurrentIndex(card.access_combo.findData("list"))
    table = card.options_table
    lengths = editor.lengths
    for label, metres in (("16 mm", 0.016), ("19 mm", 0.019)):
        table._append(label, lengths.number_text(metres))
    card._options_done()
    attr = binding.definition(app.scene, root)["nodes"][""]["attrs"]["plattenstaerke"]
    assert attr["label"] == "Plattenstärke" and attr["access"] == "list"
    assert attr["options"] == [["16 mm", pytest.approx(0.016)], ["19 mm", pytest.approx(0.019)]]
    panel.refresh()                     # the host's document hook does this
    assert ("", "plattenstaerke") in panel.options._rows


def test_attributes_editor_holds_back_a_broken_formula(shelf):
    app, root = shelf
    _make(app, root)
    panel = _panel(app, root)
    editor = panel.attributes
    editor.select("side", "x")
    card = editor._card
    card.formula_edit.setText("=Parent!Width +")
    card._formula_typed(card.formula_edit.text())
    assert card.preview.text().startswith("✗")
    before = binding.definition(app.scene, root)
    card._formula_done()
    assert editor.dirty and editor.status.text().startswith("Not applied yet")
    assert binding.definition(app.scene, root) == before
    editor.discard()
    assert not editor.dirty
    assert editor._attrs("side")["x"]["formula"] == "=Parent!Width"


def _hooked(app, panel):
    """The host's document hook: every command refreshes the panel."""
    app.viewport.notify_scene_changed = panel.refresh


def test_a_new_attribute_is_kept_when_the_selection_changes(shelf):
    app, root = shelf
    _make(app, root)
    panel = _panel(app, root)
    _hooked(app, panel)
    editor = panel.attributes
    editor.add_attribute("", None)
    card = editor._card
    card.label_edit.setText("Depth")
    card._label_typed("Depth")
    card._label_done()
    card.done_button.click()
    app.scene.selection.clear()
    panel.refresh()
    assert "depth" in binding.definition(app.scene, root)["nodes"][""]["attrs"]
    app.scene.selection.add(root)
    panel.refresh()
    assert ("", "depth") in panel.attributes._rows


def test_tab_moves_on_after_naming_a_new_attribute(shelf, qtapp):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    app, root = shelf
    _make(app, root)
    panel = _panel(app, root)
    _hooked(app, panel)
    panel.resize(420, 900)
    panel.show()
    panel.activateWindow()
    assert QTest.qWaitForWindowActive(panel)
    editor = panel.attributes
    editor.add_attribute("", None)
    card = editor._card
    card.label_edit.setFocus()
    qtapp.processEvents()
    assert qtapp.focusWidget() is card.label_edit
    card.label_edit.selectAll()
    QTest.keyClicks(card.label_edit, "Shelf gap")
    QTest.keyClick(card.label_edit, Qt.Key_Tab)
    qtapp.processEvents()
    assert editor._card is card                         # not rebuilt under the user
    assert qtapp.focusWidget() is card.name_edit
    assert card.name == "shelf_gap"
    seen = []
    for _ in range(6):
        QTest.keyClick(qtapp.focusWidget(), Qt.Key_Tab)
        qtapp.processEvents()
        seen.append(qtapp.focusWidget())
    assert seen[:4] == [card.type_combo, card._value_editor.widget,
                        card.formula_edit, card.access_combo]
    assert card.insert_button not in seen
    assert "shelf_gap" in binding.definition(app.scene, root)["nodes"][""]["attrs"]


def test_undo_refreshes_the_open_editor(shelf):
    app, root = shelf
    _make(app, root)
    panel = _panel(app, root)
    _hooked(app, panel)
    editor = panel.attributes
    editor.select("side", "x")
    card = editor._card
    card.formula_edit.setText("=Parent!Width - 0.5")
    card._formula_typed(card.formula_edit.text())
    card._formula_done()
    app.viewport.history.undo()
    panel.refresh()
    assert editor._card is not card
    assert editor._card.formula_edit.text() == "=Parent!Width"


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
