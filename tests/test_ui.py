from PySide6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QLabel, QLineEdit, QSpinBox

from fakes import SPEC, FakeApp, FakeGroup, fakes  # noqa: F401


def _app_with(group):
    app = FakeApp()
    app.groups.append(group)
    app.selection.add(group)
    return app


def test_options_widgets_by_type(qtapp, fakes):
    from dynamic_components.ui.options import OptionsForm
    group = FakeGroup(dynamic=True, last={"": {"width": 1.0}})
    form = OptionsForm(_app_with(group))
    form.show_group(group, SPEC, None)
    kinds = {key: type(row.editor.widget) for key, row in form._rows.items()
             if row.editor is not None}
    assert kinds[("", "width")] is QDoubleSpinBox
    assert kinds[("", "ratio")] is QDoubleSpinBox
    assert kinds[("", "n")] is QSpinBox
    assert kinds[("", "open")] is QCheckBox
    assert kinds[("", "style")] is QComboBox
    assert kinds[("", "note")] is QLineEdit
    assert kinds[("", "finish")] is QLineEdit
    area = form._rows[("", "area")]
    assert area.editor is None and isinstance(area.view, QLabel)
    width = form._rows[("", "width")]
    assert width.shown == 1.0
    spin = width.editor.widget
    lengths = form._lengths
    assert (spin.minimum(), spin.maximum()) == (lengths.show(0.6), lengths.show(1.2))
    assert spin.suffix() == lengths.suffix


def test_a_changed_option_is_one_undo_step_and_shows_errors(qtapp, fakes):
    from dynamic_components.ui.options import OptionsForm
    group = FakeGroup(dynamic=True)
    form = OptionsForm(_app_with(group))
    form.show_group(group, SPEC, None)
    form.apply()
    assert fakes.calls == []
    form._rows[("", "n")].editor.widget.setValue(5)
    assert fakes.calls == [("run", "Component options"),
                           ("set_values", {"": {"n": 5}})]
    errors = [w.text() for w in form.findChildren(QLabel, "error") if w.text()]
    assert errors == ["too wide"]
    combo = form._rows[("", "style")].editor.widget
    combo.setCurrentIndex(1)
    combo.activated.emit(1)
    assert fakes.calls[-1] == ("set_values", {"": {"style": "b"}})


def test_reset_shows_only_for_overridden_values(qtapp, fakes):
    from dynamic_components.ui.options import OptionsForm
    group = FakeGroup(dynamic=True)
    group.ext["dynamic_components"]["set"] = {"": {"n": 4}}
    form = OptionsForm(_app_with(group))
    form.show_group(group, SPEC, None)
    assert not form._rows[("", "n")].reset.isHidden()
    assert form._rows[("", "width")].reset.isHidden()
    form._rows[("", "n")].reset.click()
    assert fakes.calls[-1] == ("set_values", {"": {"n": None}})


def test_panel_placeholder_and_make_dynamic(qtapp, fakes):
    from dynamic_components.ui.panel import DynamicPanel
    app = FakeApp()
    panel = DynamicPanel(app)
    assert not panel.placeholder.isHidden() and panel.scroll.isHidden()
    assert panel.make_button.isHidden()
    plain = FakeGroup(dynamic=False)
    app.selection.add(plain)
    panel.refresh()
    assert not panel.make_button.isHidden() and panel.bake_button.isHidden()
    panel.make_button.click()
    assert ("make_dynamic", plain) in fakes.calls


def test_panel_header_and_bake(qtapp, fakes):
    from dynamic_components.ui.panel import DynamicPanel
    group = FakeGroup(dynamic=True)
    panel = DynamicPanel(_app_with(group))
    assert panel.title.text() == "Door"
    assert panel.subtitle.text() == "Dynamic component · 1 part"
    assert not panel.bake_button.isHidden() and not panel.scroll.isHidden()
    panel.bake_button.click()
    assert fakes.calls[-2:] == [("run", "Bake dynamic component"), ("bake", group)]


def test_attribute_rows_are_readable(qtapp, fakes):
    from dynamic_components.ui.panel import DynamicPanel
    group = FakeGroup(dynamic=True)
    panel = DynamicPanel(_app_with(group))
    rows = panel.attributes._rows
    assert rows[("", "width")].title.text() == "Width"
    assert rows[("", "open")].value.text() == "No"
    assert rows[("leaf", "lenx")].title.text() == "Size X"
    assert rows[("leaf", "lenx")].detail.full() == "=Parent!width"
    assert rows[("", "width")].detail.full() == "Option for users"
    titles = [f.header.text() for f in panel.attributes._folds.values()]
    assert titles == ["Attributes: Door  (8)", "Part: Leaf  (1)"]


def test_references_offer_every_readable_value(qtapp, fakes):
    from dynamic_components.ui.panel import DynamicPanel
    group = FakeGroup(dynamic=True)
    panel = DynamicPanel(_app_with(group))
    refs = dict((path, text) for path, text in panel.attributes.references("leaf"))
    assert refs[("Component", "Width")] == "Parent!width"
    assert refs[("Component", "Size Z")] == "Parent!lenz"
    assert refs[("This part", "Size X")] == "lenx"
    assert refs[("This part", "Copy number (0 = original)")] == "copy"
    root = dict((path, text) for path, text in panel.attributes.references(""))
    assert root[("Component", "Width")] == "width"
    assert root[("Other parts", "Leaf", "Size X")] == "leaf!lenx"


def test_card_applies_finished_edits_and_holds_back_broken_formulas(qtapp, fakes):
    from dynamic_components.ui.panel import DynamicPanel
    group = FakeGroup(dynamic=True)
    panel = DynamicPanel(_app_with(group))
    editor = panel.attributes
    editor.select("", "width")
    card = editor._card
    assert card.name_edit is None and card.type_combo is not None
    card.formula_edit.setText("=IF(")
    card._formula_typed(card.formula_edit.text())
    assert card.preview.text() == "✗ unbalanced"
    card._formula_done()
    assert editor.status.text().startswith("Not applied yet") and not any(
        c[0] == "set_definition" for c in fakes.calls)
    card.formula_edit.setText("=1+1")
    card._formula_typed(card.formula_edit.text())
    assert not any(c[0] == "set_definition" for c in fakes.calls)   # typing only
    card._formula_done()
    card.max_edit.setText("2")
    card._limit_done("max", card.max_edit)
    kind, def_id, new = fakes.calls[-1]
    attr = new["nodes"][""]["attrs"]["width"]
    assert (kind, def_id) == ("set_definition", "d1")
    assert attr["formula"] == "=1+1" and attr["min"] == 0.6
    assert attr["max"] == editor.lengths.si(2.0)
    assert len([c for c in fakes.calls if c[0] == "set_definition"]) == 2


def test_slug_makes_formula_names_from_labels():
    from dynamic_components.ui.attributes import slug
    assert slug("Plattenstärke") == "plattenstaerke"
    assert slug("Höhe innen (mm)") == "hoehe_innen_mm"
    assert slug("2 Böden") == "a_2_boeden"


def test_formula_completion_replaces_only_the_word(qtapp):
    from dynamic_components.ui.attributes import FormulaEdit
    edit = FormulaEdit()
    edit.set_words(["Parent!width", "Parent!lenz", "IF("])
    edit.setText("=2*Par + 1")
    edit.setCursorPosition(len("=2*Par"))
    edit._complete_with("Parent!width")
    assert edit.text() == "=2*Parent!width + 1"
    edit.setText("")
    edit.insert_text("MAX()", 1)
    assert edit.text() == "=MAX()" and edit.cursorPosition() == 5


def test_options_table_reads_lengths_in_document_units(qtapp):
    from dynamic_components.ui.attributes import OptionsTable
    from dynamic_components.ui.common import Lengths
    lengths = Lengths()
    table = OptionsTable("length", [["Thin", 0.016]], lengths, lambda: None)
    assert table.table.item(0, 1).text() == lengths.number_text(0.016)
    table._append("Thick", lengths.number_text(0.025))
    table._append("", "")                       # an empty row is ignored
    assert [o[0] for o in table.options()] == ["Thin", "Thick"]
    assert abs(table.options()[1][1] - 0.025) < 1e-9
    table._append("Bad", "abc")
    try:
        table.options()
    except ValueError as exc:
        assert "Choice 4" in str(exc)
    else:
        raise AssertionError("a bad value must be reported")


def test_panel_offers_loose_groups_as_parts(qtapp, fakes):
    from types import SimpleNamespace
    from dynamic_components.ui.panel import DynamicPanel
    group = FakeGroup(dynamic=True)
    group.loose = [SimpleNamespace(name="Group 1")]
    panel = DynamicPanel(_app_with(group))
    assert not panel.loose_box.isHidden()
    assert "“Group 1” is in the component" in panel.loose_label.text()
    panel.attributes.dirty = True
    panel.refresh()
    assert not panel.loose_button.isEnabled()
    panel.attributes.dirty = False
    panel.refresh()
    panel.loose_button.click()
    assert fakes.calls[-2:] == [("run", "Add parts to dynamic component"),
                                ("add_parts", group)]
