"""The extension loads into a real IngeTrazo MainWindow and its entries work."""
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent
from PySide6.QtGui import QMatrix4x4, QVector3D as V
from PySide6.QtWidgets import QApplication, QMenu

from core.group import Group
from core.mesh import Mesh

from dynamic_components import binding


@pytest.fixture
def win(qtapp, monkeypatch):
    from core import extensions
    root = Path(__file__).resolve().parents[1]
    monkeypatch.setattr(extensions, "plugin_dirs", lambda: [root])
    from views.main_window import MainWindow
    w = MainWindow()
    yield w
    w._saved_version = w.viewport.scene.version
    w.close()
    w.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def _component(scene):
    m = Mesh()
    m.add_face([V(0, 0, 0), V(1, 0, 0), V(1, 1, 0), V(0, 1, 0)])
    part = Group(m, "Leaf")
    part.xform = QMatrix4x4()
    part.component = False
    root = Group(Mesh(), "Door")
    root.adopt([part])
    scene.groups.append(root)
    return root


_menus = []


def _entries(win, group):
    menu = QMenu()
    _menus.append(menu)  # the actions die with their menu
    for fn in win._ext_context_menus:
        fn(menu, {group})
    return {a.text(): a for a in menu.actions()}


def test_loads_and_makes_dynamic_from_context_menu(win):
    assert any(d.objectName() == "extension_dynamic_components"
               for d in win._extension_docks)
    scene = win.viewport.scene
    root = _component(scene)
    entries = _entries(win, root)
    assert set(entries) == {"Make Dynamic"}
    entries["Make Dynamic"].trigger()
    assert binding.is_dynamic(root)
    assert set(_entries(win, root)) == {"Component Options…",
                                        "Bake Dynamic Component"}
    win.viewport.history.undo()
    assert not binding.is_dynamic(root)


def test_scaling_a_dynamic_instance_moves_scale_into_lenx(win):
    scene = win.viewport.scene
    root = _component(scene)
    spec = {"version": 1, "name": "Door", "nodes": {
        "": {"attrs": {}},
        "leaf": {"attrs": {"lenx": {"type": "length", "value": 1.0,
                                    "formula": "=Parent!LenX"}}}}}
    binding.run(win.viewport, lambda s: binding.make_dynamic(s, root, spec),
                [root], "Make dynamic")
    from core.history import SnapshotImport
    win.viewport.history.execute(
        SnapshotImport(lambda s: root.xform.scale(3.0, 1.0, 1.0)))
    win.viewport.notify_scene_changed()
    assert root.xform.column(0).toVector3D().length() == pytest.approx(1.0)
    assert root.ext[binding.KEY]["set"][""]["lenx"] == pytest.approx(3.0)
    assert root.children[0].xform.column(0).toVector3D().length() == pytest.approx(3.0)
    # Undoing the absorption must not re-absorb the scale it brings back.
    win.viewport.history.undo()
    win.viewport.notify_scene_changed()
    assert root.xform.column(0).toVector3D().length() == pytest.approx(3.0)


def test_scale_preview_frames_make_no_undo_steps_and_commit_absorbs_once(win):
    """Like the Scale tool: every mouse move rewrites the xform from the grip's
    original and the viewport reports a change; only the release commits a
    ScaleGroupCommand. Absorbing per frame once made thousands of undo steps
    and multiplied LenZ frame after frame."""
    from core.history import ScaleGroupCommand
    scene = win.viewport.scene
    m = Mesh()
    c = [V(x, y, z) for z in (0, 0.5) for y in (0, 0.4) for x in (0, 0.6)]
    for idx in ((0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4),
                (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)):
        m.add_face([c[i] for i in idx])
    part = Group(m, "Leaf")
    part.xform = QMatrix4x4()
    part.component = False
    root = Group(Mesh(), "Box")
    root.adopt([part])
    scene.groups.append(root)
    spec = {"version": 1, "name": "Door", "nodes": {
        "": {"attrs": {}},
        "leaf": {"attrs": {"lenz": {"type": "length", "value": 1.0,
                                    "formula": "=Parent!LenZ"}}}}}
    binding.run(win.viewport, lambda s: binding.make_dynamic(s, root, spec),
                [root], "Make dynamic")
    win.viewport.notify_scene_changed()
    hist = win.viewport.history
    steps = len(hist.undo_stack)
    original = QMatrix4x4(root.xform)
    for factor in (1.05, 1.2, 1.5, 1.8, 2.0):
        preview = QMatrix4x4()
        preview.scale(1.0, 1.0, factor)
        root.xform = preview * original
        scene.version += 1
        win.viewport.notify_scene_changed()
    assert len(hist.undo_stack) == steps
    assert not root.ext[binding.KEY]["set"]
    root.xform = QMatrix4x4(original)            # the tool reverts, then commits
    hist.execute(ScaleGroupCommand(root, V(0, 0, 0), (1.0, 1.0, 2.0)))
    win.viewport.notify_scene_changed()
    assert len(hist.undo_stack) == steps + 2      # the scale and its absorption
    assert root.ext[binding.KEY]["set"][""]["lenz"] == pytest.approx(1.0)
    leaf = root.children[0]
    assert leaf.xform.column(2).toVector3D().length() == pytest.approx(2.0)
    assert root.xform.column(2).toVector3D().length() == pytest.approx(1.0)
    win.viewport.notify_scene_changed()
    assert len(hist.undo_stack) == steps + 2


def _slab(name, size, at):
    lx, ly, lz = size
    m = Mesh()
    c = [V(x, y, z) for z in (0, lz) for y in (0, ly) for x in (0, lx)]
    for idx in ((0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4),
                (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)):
        m.add_face([c[i] for i in idx])
    g = Group(m, name)
    g.xform = QMatrix4x4()
    g.xform.translate(*at)
    g.component = False
    return g


def _world_width(root, part, rest_x):
    world = root.xform * part.xform
    return world.column(0).toVector3D().length() * rest_x, world.map(V(0, 0, 0)).x()


def test_live_scale_preview_keeps_board_thickness_and_cancels_cleanly(win):
    from core.history import ScaleGroupCommand
    scene = win.viewport.scene
    T, W = 0.02, 1.0
    side = _slab("Side", (T, 0.5, 1.0), (W - T, 0, 0))
    board = _slab("Board", (W, 0.5, T), (0, 0, 0))
    root = Group(Mesh(), "Carcass")
    root.adopt([side, board])
    scene.groups.append(root)
    spec = {"version": 1, "name": "Carcass", "nodes": {
        "": {"attrs": {}},
        "side": {"attrs": {
            "x": {"type": "length", "value": W - T, "formula": f"=Parent!LenX - {T}"},
            "lenx": {"type": "length", "value": T, "formula": f"={T}"}}},
        "board": {"attrs": {
            "lenx": {"type": "length", "value": W, "formula": "=Parent!LenX"}}}}}
    binding.run(win.viewport, lambda s: binding.make_dynamic(s, root, spec),
                [root], "Make dynamic")
    binding.run(win.viewport, lambda s: binding.apply(s, root), [root], "Apply")
    win.viewport.notify_scene_changed()
    hist = win.viewport.history
    steps = len(hist.undo_stack)
    original = QMatrix4x4(root.xform)

    def frame(factor):
        preview = QMatrix4x4()
        preview.scale(factor, 1.0, 1.0)
        root.xform = preview * original
        scene.version += 1
        win.viewport.notify_scene_changed()

    for factor in (1.2, 1.6, 2.0):
        frame(factor)
        width, x = _world_width(root, side, T)
        assert width == pytest.approx(T)                 # the wall stays thin
        assert x == pytest.approx(factor * W - T)        # and sits at the edge
        assert _world_width(root, board, W)[0] == pytest.approx(factor * W)
    assert len(hist.undo_stack) == steps and not root.ext[binding.KEY]["set"]

    frame(1.0)                                           # Esc: the tool reverts
    assert _world_width(root, side, T) == (pytest.approx(T), pytest.approx(W - T))
    assert _world_width(root, board, W)[0] == pytest.approx(W)

    frame(2.0)
    root.xform = QMatrix4x4(original)                    # release: revert, commit
    hist.execute(ScaleGroupCommand(root, V(0, 0, 0), (2.0, 1.0, 1.0)))
    win.viewport.notify_scene_changed()
    assert len(hist.undo_stack) == steps + 2
    assert root.ext[binding.KEY]["set"][""]["lenx"] == pytest.approx(2 * W)
    assert root.xform.column(0).toVector3D().length() == pytest.approx(1.0)
    assert _world_width(root, side, T) == (pytest.approx(T), pytest.approx(2 * W - T))

    hist.undo()                                          # the absorption
    win.viewport.notify_scene_changed()
    assert _world_width(root, side, T) == (pytest.approx(T), pytest.approx(2 * W - T))
    hist.undo()                                          # the scale itself
    win.viewport.notify_scene_changed()
    assert root.xform.column(0).toVector3D().length() == pytest.approx(1.0)
    assert _world_width(root, side, T) == (pytest.approx(T), pytest.approx(W - T))
    assert _world_width(root, board, W)[0] == pytest.approx(W)
    assert len(hist.undo_stack) == steps


def test_a_group_moved_into_the_component_can_become_a_part(win):
    scene = win.viewport.scene
    root = _component(scene)
    binding.run(win.viewport, lambda s: binding.make_dynamic(s, root),
                [root], "Make dynamic")
    extra = _slab("Shelf board", (0.5, 0.3, 0.02), (0.1, 0, 0.4))
    root.children = list(root.children) + [extra]
    assert binding.loose_children(root) == [extra]
    binding.run(win.viewport, lambda s: binding.add_parts(s, root), [root], "Add parts")
    assert binding.loose_children(root) == []
    node = binding.definition(scene, root)["nodes"]["shelf_board"]
    assert node["label"] == "Shelf board"
    assert node["rest"]["size"] == pytest.approx([0.5, 0.3, 0.02])
    win.viewport.history.undo()
    assert binding.loose_children(root) == [extra]
    assert "shelf_board" not in binding.definition(scene, root)["nodes"]


def _dynamic_carcass(win):
    scene = win.viewport.scene
    root = Group(Mesh(), "Carcass")
    root.adopt([_slab("Side", (0.02, 0.5, 1.0), (0, 0, 0))])
    root.component = True
    root.xform.translate(2.0, 0, 0)
    scene.groups.append(root)
    binding.run(win.viewport, lambda s: binding.make_dynamic(s, root), [root], "Make")
    return root


def test_add_a_group_to_a_dynamic_component_keeps_it_in_place(win):
    from core.group import world_mesh
    scene = win.viewport.scene
    root = _dynamic_carcass(win)
    shelf = _slab("Shelf board", (0.5, 0.3, 0.02), (2.1, 0.0, 0.4))
    classic = Group(Mesh(), "Loose face")
    classic.mesh.add_face([V(2.1, 0, 0.8), V(2.4, 0, 0.8), V(2.4, 0.3, 0.8)])
    scene.groups.extend([shelf, classic])
    before = [sorted((round(v.position.x(), 6), round(v.position.y(), 6),
                      round(v.position.z(), 6)) for v in world_mesh(g).vertices)
              for g in (shelf, classic)]
    hist = win.viewport.history
    steps = len(hist.undo_stack)
    assert binding.add_problem(scene, [shelf, classic], root) is None
    names = binding.add_to_component(win.viewport, [shelf, classic], root)
    assert names == ["shelf_board", "loose_face"]
    assert len(hist.undo_stack) == steps + 1
    assert shelf not in scene.groups and shelf in root.children
    assert binding.loose_children(root) == []
    nodes = binding.definition(scene, root)["nodes"]
    assert nodes["shelf_board"]["rest"]["size"] == pytest.approx([0.5, 0.3, 0.02])

    def world(g):
        m = root.xform * g.xform
        return sorted((round(m.map(v.position).x(), 6), round(m.map(v.position).y(), 6),
                       round(m.map(v.position).z(), 6)) for v in g.mesh.vertices)
    assert [world(shelf), world(classic)] == before   # nothing moved in the world
    hist.undo()
    assert shelf in scene.groups and classic in scene.groups
    assert shelf not in root.children
    assert "shelf_board" not in binding.definition(scene, root)["nodes"]
    hist.redo()
    assert shelf in root.children and "shelf_board" in binding.definition(scene, root)["nodes"]


def test_add_problems(win):
    scene = win.viewport.scene
    root = _dynamic_carcass(win)
    other = _dynamic_carcass(win)
    part = root.children[0]
    assert "itself" in binding.add_problem(scene, [root], root)
    assert "nested dynamic" in binding.add_problem(scene, [other], root)
    assert "already" in binding.add_problem(scene, [part], root)
    assert "another dynamic component" in binding.add_problem(scene, [part], other)
    locked = _slab("Locked", (0.1, 0.1, 0.1), (0, 0, 0))
    locked.locked = True
    scene.groups.append(locked)
    assert "locked" in binding.add_problem(scene, [locked], root)
    assert "not a dynamic" in binding.add_problem(scene, [locked], locked)
    with pytest.raises(ValueError):
        binding.add_to_component(win.viewport, [part], root)


def test_add_dialog_lists_only_components_that_accept(win):
    from dynamic_components.ui.add_dialog import AddDialog
    scene = win.viewport.scene
    root = _dynamic_carcass(win)
    other = _dynamic_carcass(win)
    other.locked = True
    loose = _slab("Board", (0.1, 0.1, 0.1), (0, 0, 0))
    scene.groups.append(loose)
    dialog = AddDialog(scene, [loose], binding.dynamic_roots(scene))
    assert dialog.list.count() == 1 and dialog.chosen() is root
    assert dialog.list.item(0).text() == "Carcass  ·  1 part"


def _panel_of(win):
    return next(w for w in QApplication.allWidgets()
                if type(w).__name__ == "DynamicPanel" and w.window() is win)


def _shelf_at(win, x):
    scene = win.viewport.scene
    side = _slab("Side", (0.02, 0.5, 1.0), (0.98, 0, 0))
    board = _slab("Board", (1.0, 0.5, 0.02), (0, 0, 0))
    root = Group(Mesh(), "Shelf")
    root.adopt([side, board])
    root.component = True
    root.xform.translate(x, 0, 0)
    scene.groups.append(root)
    spec = {"version": 1, "name": "Shelf", "nodes": {
        "": {"attrs": {"boards": {"type": "int", "value": 1, "access": "textbox"}}},
        "side": {"attrs": {"x": {"type": "length", "value": 0.98,
                                 "formula": "=Parent!LenX - 0.02"}}},
        "board": {"attrs": {"lenx": {"type": "length", "value": 1.0,
                                     "formula": "=Parent!LenX"},
                            "copies": {"type": "int", "value": 0,
                                       "formula": "=Parent!boards - 1"}}}}}
    binding.run(win.viewport, lambda s: binding.make_dynamic(s, root, spec), [root], "Make")
    binding.run(win.viewport, lambda s: binding.apply(s, root), [root], "Apply")
    win.viewport.notify_scene_changed()
    return root, side


def test_editing_inside_a_dynamic_component_and_leaving_moves_nothing(win):
    scene = win.viewport.scene
    root, side = _shelf_at(win, 5.0)
    world = lambda: (root.xform * side.xform).map(V(0, 0, 0)).x()  # noqa: E731
    assert world() == pytest.approx(5.98)
    panel = _panel_of(win)
    scene.begin_group_edit(root)            # the host pushes the matrix down
    win.viewport.notify_scene_changed()
    assert root.xform.column(3).x() == pytest.approx(0.0)
    assert world() == pytest.approx(5.98)   # left alone while open
    assert panel.group is root and not panel.open_note.isHidden()
    assert not panel.scroll.widget().isEnabled() and not panel.bake_button.isEnabled()
    scene.end_group_edit()
    win.viewport.notify_scene_changed()
    assert root.xform.column(3).x() == pytest.approx(5.0)   # pulled back up
    assert world() == pytest.approx(5.98)
    binding.run(win.viewport,
                lambda s: binding.set_values(s, root, {"": {"boards": 3}}),
                [root], "Options")
    assert world() == pytest.approx(5.98)   # no jump to the origin


def test_deleting_a_part_updates_the_sidebar(win):
    scene = win.viewport.scene
    root, side = _shelf_at(win, 2.0)
    panel = _panel_of(win)
    scene.selection.clear()
    scene.selection.add(root)
    win.viewport.notify_scene_changed()
    assert set(panel.attributes._folds) == {"", "side", "board"}
    assert panel.missing_box.isHidden()
    root.children = [c for c in root.children if c is not side]   # deleted
    win.viewport.notify_scene_changed()
    assert set(panel.attributes._folds) == {"", "board"}
    assert panel.subtitle.text() == "Dynamic component · 1 part"
    assert not panel.missing_box.isHidden() and "“Side”" in panel.missing_label.text()
    panel.missing_button.click()
    assert "side" not in binding.definition(scene, root)["nodes"]
    win.viewport.notify_scene_changed()
    assert panel.missing_box.isHidden()
    win.viewport.history.undo()
    win.viewport.notify_scene_changed()
    assert "side" in binding.definition(scene, root)["nodes"]


def _insert_cabinet(win, lang):
    """The reference cabinet, built by its script, into the window's document."""
    from cabinet_builder import build
    scene = win.viewport.scene
    made = []
    binding.run(win.viewport, lambda s: made.append(build.insert_cabinet(s, lang=lang)),
                [], "Insert cabinet")
    scene.selection.clear()
    scene.selection.add(made[0])
    win.viewport.notify_scene_changed()
    return made[0]


def test_the_panel_speaks_german(win):
    """The extension follows the host's language (the host loads it under a
    module name of its own, so only the host setting reaches it)."""
    from core import i18n as host_i18n
    from dynamic_components.ui.panel import DynamicPanel
    previous = host_i18n.current_language()
    host_i18n.set_language("de")
    try:
        _insert_cabinet(win, "de")
        panel = DynamicPanel(_app_for(win))
        assert panel.bake_button.text() == "Einfrieren"
        assert set(panel.options._headers) == {"Korpus", "Sockel", "Fachböden", "Trennwände",
                                               "Bohrungen (System 32)"}
        assert panel.title.text() == "Schrank"
    finally:
        host_i18n.set_language(previous)


def _app_for(win):
    from types import SimpleNamespace
    return SimpleNamespace(scene=win.viewport.scene, viewport=win.viewport,
                           key=binding.KEY, window=win)
