from types import SimpleNamespace

import pytest
from PySide6.QtGui import QMatrix4x4

from fakes import FakeApp, FakeGroup, fakes  # noqa: F401


class Menu:
    def __init__(self):
        self.actions = {}

    def addAction(self, text, fn):
        self.actions[text] = fn


def _setup(qtapp, fakes):
    import dynamic_components
    app = FakeApp()
    dynamic_components.setup(app)
    return app


def test_registers_everything(qtapp, fakes):
    app = _setup(qtapp, fakes)
    assert app.panels[0][0] == "Dynamic Components"
    assert app.panels[0][2] == {"start_hidden": True}
    assert len(app.context_fns) == len(app.outliner_fns) == len(app.document_hooks) == 1


def test_rejects_other_api_version(qtapp, fakes):
    import dynamic_components
    app = FakeApp()
    app.api_version = 1
    with pytest.raises(RuntimeError):
        dynamic_components.setup(app)


def test_context_menu_entries(qtapp, fakes):
    app = _setup(qtapp, fakes)
    menu_fn = app.context_fns[0]

    def entries(selection):
        menu = Menu()
        menu_fn(menu, selection)
        return menu

    assert entries([]).actions == {}
    assert entries([FakeGroup(), FakeGroup()]).actions == {}
    assert entries([FakeGroup(component=False)]).actions == {}
    plain = FakeGroup()
    menu = entries([plain])
    assert list(menu.actions) == ["Make Dynamic"]
    menu.actions["Make Dynamic"]()
    assert fakes.calls == [("run", "Make dynamic"), ("make_dynamic", plain)]
    dynamic = FakeGroup(dynamic=True)
    menu = entries([dynamic])
    assert list(menu.actions) == ["Component Options…", "Bake Dynamic Component"]
    menu.actions["Bake Dynamic Component"]()
    assert fakes.calls[-1] == ("bake", dynamic)


def test_outliner_kind(qtapp, fakes):
    app = _setup(qtapp, fakes)
    kind = app.outliner_fns[0]
    assert kind(FakeGroup()) is None
    info = kind(FakeGroup(dynamic=True, last={"": {"width": 1.1}}))
    assert info["type"] == "Dynamic component"
    assert ("Width", "1.1") in info["props"]


def test_document_hook_absorbs_scale_once_without_reentrancy(qtapp, fakes):
    app = _setup(qtapp, fakes)
    hook = app.document_hooks[0]
    scaled = QMatrix4x4()
    scaled.scale(2.0, 1.0, 1.0)
    group = FakeGroup(dynamic=True, xform=scaled)
    unit = FakeGroup(dynamic=True, xform=QMatrix4x4())
    app.groups.extend([group, unit])
    # the command's own notification fires the hook again
    original = fakes.run

    def run(viewport, mutate, roots, label=""):
        original(viewport, mutate, roots, label)
        hook()
    fakes.run = run
    hook()
    assert [c for c in fakes.calls if c[0] == "absorb"] == [("absorb", group)]
    hook()
    assert len([c for c in fakes.calls if c[0] == "absorb"]) == 1
