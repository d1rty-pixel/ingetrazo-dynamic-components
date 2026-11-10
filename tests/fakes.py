"""Fakes for binding/spec/formula/evaluate so UI tests do not depend on them."""
import sys
import types
from types import SimpleNamespace

import pytest

KEY = "dynamic_components"

SPEC = {
    "version": 1, "name": "Door",
    "nodes": {
        "": {"attrs": {
            "width": {"label": "Width", "type": "length", "value": 0.9,
                      "formula": None, "access": "textbox", "min": 0.6, "max": 1.2},
            "n": {"label": "Count", "type": "int", "value": 2,
                  "formula": None, "access": "textbox"},
            "open": {"label": "Open", "type": "bool", "value": False,
                     "formula": None, "access": "textbox"},
            "ratio": {"label": "Ratio", "type": "float", "value": 1.5,
                      "formula": None, "access": "textbox"},
            "style": {"label": "Style", "type": "choice", "value": "a",
                      "formula": None, "access": "list",
                      "options": [["Plain", "a"], ["Fancy", "b"]]},
            "note": {"label": "Note", "type": "string", "value": "hi",
                     "formula": None, "access": "textbox"},
            "finish": {"label": "Finish", "type": "material", "value": "oak",
                       "formula": None, "access": "textbox"},
            "area": {"label": "Area", "type": "float", "value": 1.0,
                     "formula": "=width*2", "access": "view"},
        }},
        "leaf": {"label": "Leaf", "attrs": {
            "lenx": {"label": "LenX", "type": "length", "value": 0.9,
                     "formula": "=Parent!width", "access": "none"}}},
    },
}


class FakeSpecError(Exception):
    pass


class FakeFormulaError(Exception):
    pass


def fake_modules(spec=SPEC):
    calls = []
    editable = [(n, a, body["attrs"][a]) for n, body in spec["nodes"].items()
                for a in body["attrs"]
                if body["attrs"][a]["access"] in ("textbox", "list")]
    binding = types.ModuleType("binding")
    binding.calls = calls
    binding.definition = lambda scene, group: spec
    binding.is_dynamic = lambda group: KEY in group.ext
    binding.instances_of = lambda scene, def_id: [object()]

    def set_values(scene, group, values):
        calls.append(("set_values", values))
        return SimpleNamespace(errors={("", "width"): "too wide"})
    binding.set_values = set_values
    binding.set_definition = lambda s, d, new: calls.append(("set_definition", d, new))
    binding.make_dynamic = lambda s, g: calls.append(("make_dynamic", g))
    binding.bake = lambda s, g: calls.append(("bake", g))
    binding.absorb_scale = lambda s, g: calls.append(("absorb", g)) or True
    binding.absorbable_axes = lambda s, g: [0]
    binding.preview_scale = lambda s, g: calls.append(("preview", g)) or True
    binding.relayout = lambda s, g: calls.append(("relayout", g)) or False
    binding.loose_children = lambda g: list(getattr(g, "loose", []))
    binding.add_parts = lambda s, g: calls.append(("add_parts", g)) or ["new"]
    binding.holder = lambda s, g: getattr(g, "holder", None)
    binding.is_open = lambda s, g: getattr(g, "open", False)
    binding.settle = lambda s, g: False
    binding.present_parts = lambda g: set(getattr(g, "present", {"leaf"}))
    binding.missing_parts = lambda s, g: list(getattr(g, "missing", []))
    binding.remove_parts = lambda s, g, names: calls.append(("remove_parts", g, list(names)))
    binding.dynamic_roots = lambda s: list(getattr(s, "dynamic_roots", []))
    binding.add_problem = lambda s, gs, r: getattr(r, "problem", None)
    binding.edited_parts = lambda g: list(getattr(g, "edited", []))
    binding.problems = lambda g: dict(getattr(g, "problems", {}))
    binding.regenerate = lambda s, g: calls.append(("regenerate", g)) or 1

    def add_to_component(viewport, groups, root, label=""):
        calls.append(("add_to_component", list(groups), root))
        return ["new"]
    binding.add_to_component = add_to_component

    def run(viewport, mutate, roots, label="Dynamic component"):
        calls.append(("run", label))
        mutate(viewport.scene)
        history = getattr(viewport, "history", None)
        if history is not None:
            history.undo_stack.append(("command", label))
    binding.run = run

    spec_mod = types.ModuleType("spec")
    spec_mod.SpecError = FakeSpecError
    spec_mod.editable_attrs = lambda s: editable
    spec_mod.normalize = lambda s: s
    spec_mod.coerce = lambda attr, value: value

    formula = types.ModuleType("formula")
    formula.FormulaError = FakeFormulaError

    def parse(source):
        if "(" in source and ")" not in source:
            raise FakeFormulaError("unbalanced")
    formula.parse = parse
    formula.FUNCTIONS = ("IF", "MAX", "MIN")

    evaluate = types.ModuleType("evaluate")
    evaluate.evaluate = lambda s, o, last=None: SimpleNamespace(errors={})
    return binding, spec_mod, formula, evaluate


@pytest.fixture
def fakes(monkeypatch):
    import dynamic_components
    mods = fake_modules()
    for name, mod in zip(("binding", "spec", "formula", "evaluate"), mods):
        monkeypatch.setitem(sys.modules, f"dynamic_components.{name}", mod)
        monkeypatch.setattr(dynamic_components, name, mod, raising=False)
    return mods[0]


class FakeGroup:
    def __init__(self, dynamic=False, component=True, xform=None, last=None):
        self.ext = {KEY: {"def": "d1", "set": {}, "last": last or {}}} if dynamic else {}
        self.xform = xform
        self._component = component

    def is_component(self):
        return self._component


class FakeApp:
    api_version = 2
    key = "dynamic_components"

    def __init__(self):
        self.groups = []
        self.selection = set()
        self.scene = SimpleNamespace(groups=self.groups, selection=self.selection,
                                     version=0)
        self.viewport = SimpleNamespace(scene=self.scene,
                                        history=SimpleNamespace(undo_stack=[]))
        self.window = None
        self.panels = []
        self.context_fns = []
        self.outliner_fns = []
        self.document_hooks = []

    def add_panel(self, title, widget, name=None, **kw):
        self.panels.append((title, widget, kw))
        return object()

    def add_context_menu(self, fn):
        self.context_fns.append(fn)

    def add_outliner_kind(self, fn):
        self.outliner_fns.append(fn)

    def on_document_changed(self, fn):
        self.document_hooks.append(fn)

    def add_menu(self, title):
        from PySide6.QtWidgets import QMenu
        menu = QMenu(title)
        self.menus = getattr(self, "menus", [])
        self.menus.append(menu)
        return menu
