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
    scene.begin_group_edit(root)            # the host pushes the matrix down
    win.viewport.notify_scene_changed()
    assert root.xform.column(3).x() == pytest.approx(0.0)
    assert world() == pytest.approx(5.98)   # left alone while open
    scene.end_group_edit()
    win.viewport.notify_scene_changed()
    assert root.xform.column(3).x() == pytest.approx(5.0)   # pulled back up
    assert world() == pytest.approx(5.98)
    binding.run(win.viewport,
                lambda s: binding.set_values(s, root, {"": {"boards": 3}}),
                [root], "Options")
    assert world() == pytest.approx(5.98)   # no jump to the origin
