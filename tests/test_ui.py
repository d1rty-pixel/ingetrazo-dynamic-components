from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QLabel,
                               QLineEdit, QSpinBox)

from fakes import FakeApp, FakeGroup, fakes  # noqa: F401


def _app_with(group):
    app = FakeApp()
    app.groups.append(group)
    app.selection.add(group)
    return app


def test_options_dialog_widgets_by_type(qtapp, fakes):
    from dynamic_components.ui.options import OptionsDialog
    group = FakeGroup(dynamic=True, last={"": {"width": 1.0}})
    dialog = OptionsDialog(_app_with(group), group)
    assert dialog.windowTitle() == "Component Options — Door"
    kinds = {key: type(read.__self__) for key, (read, _) in dialog._rows.items()}
    assert kinds[("", "width")] is QDoubleSpinBox
    assert kinds[("", "ratio")] is QDoubleSpinBox
    assert kinds[("", "n")] is QSpinBox
    assert kinds[("", "open")] is QCheckBox
    assert kinds[("", "style")] is QComboBox
    assert kinds[("", "note")] is QLineEdit
    assert kinds[("", "finish")] is QLineEdit
    assert ("", "area") not in dialog._rows
    assert dialog._rows[("", "width")][1] == 1.0
    spin = next(r[0].__self__ for k, r in dialog._rows.items() if k == ("", "width"))
    assert (spin.minimum(), spin.maximum()) == (0.6, 1.2)


def test_apply_passes_only_changed_values(qtapp, fakes):
    from dynamic_components.ui.options import OptionsDialog
    group = FakeGroup(dynamic=True)
    dialog = OptionsDialog(_app_with(group), group)
    dialog.apply()
    assert fakes.calls == []
    read = dialog._rows[("", "n")][0]
    read.__self__.setValue(5)
    dialog._rows[("", "style")][0].__self__.setCurrentIndex(1)
    dialog.apply()
    assert fakes.calls == [("run", "Component options"),
                           ("set_values", {"": {"n": 5, "style": "b"}})]
    errors = [w.text() for w in dialog.findChildren(QLabel, "error")]
    assert errors == ["too wide"]
    assert dialog.changed_values() == {}


def test_panel_placeholder_without_selection(qtapp, fakes):
    from dynamic_components.ui.attributes import AttributesPanel
    app = FakeApp()
    panel = AttributesPanel(app)
    panel.show()
    assert panel.placeholder.isVisible() and not panel.tree.isVisible()
    app.selection.add(FakeGroup(dynamic=False))
    panel.refresh()
    assert panel.placeholder.isVisible()


def test_panel_shows_spec_and_applies_edit(qtapp, fakes):
    from dynamic_components.ui.attributes import AttributesPanel
    group = FakeGroup(dynamic=True, last={"": {"width": 1.1}})
    panel = AttributesPanel(_app_with(group))
    panel.show()
    assert not panel.placeholder.isVisible()
    root = panel.tree.topLevelItem(0)
    assert root.text(0) == "Door" and panel.tree.topLevelItem(1).text(0) == "Leaf"
    assert root.child(0).text(0) == "Width" and root.child(0).text(1) == "1.1"
    panel.tree.setCurrentItem(root.child(0))
    assert panel.name_edit.text() == "width"
    panel.formula_edit.setText("=IF(")
    panel.set_attribute()
    assert panel.status.text() == "unbalanced"
    panel.formula_edit.setText("=1+1")
    panel.options_edit.setText("A=1; B=2")
    panel.set_attribute()
    panel.apply()
    kind, def_id, new = fakes.calls[-1]
    attr = new["nodes"][""]["attrs"]["width"]
    assert (kind, def_id) == ("set_definition", "d1")
    assert attr["formula"] == "=1+1" and attr["options"] == [["A", 1.0], ["B", 2.0]]
    assert attr["min"] == 0.6
