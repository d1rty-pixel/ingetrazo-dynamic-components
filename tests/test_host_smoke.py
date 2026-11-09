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
