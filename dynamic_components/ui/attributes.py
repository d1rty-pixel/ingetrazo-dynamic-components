"""Authoring panel: the spec of the selected dynamic instance."""
from __future__ import annotations

import copy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from ..i18n import tr

KEY = "dynamic_components"
TYPES = ("length", "float", "int", "bool", "string", "choice", "material")
ACCESS = ("none", "view", "textbox", "list")
_NODE_ROLE = Qt.UserRole
_ATTR_ROLE = Qt.UserRole + 1


def _modules():
    from .. import binding, formula, spec
    return binding, formula, spec


def _text(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _convert(kind, text):
    text = text.strip()
    if kind in ("length", "float"):
        return float(text)
    if kind == "int":
        return int(float(text))
    if kind == "bool":
        return text.lower() in ("1", "true", "yes", "on")
    return text


def _format_options(options):
    return "; ".join(f"{label}={_text(value)}" for label, value in options or [])


def _parse_options(kind, text):
    options = []
    for chunk in filter(None, (c.strip() for c in text.split(";"))):
        label, sep, raw = chunk.partition("=")
        if not sep:
            raise ValueError(tr("Option must look like Label=value: ") + chunk)
        options.append([label.strip(), _convert(kind, raw)])
    return options


class AttributesPanel(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self._group = None
        self._def_id = None
        self._work = None
        self._dirty = False
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        self.placeholder = QLabel(tr("Select a dynamic component to edit its "
                                     "attributes."))
        self.placeholder.setWordWrap(True)
        layout.addWidget(self.placeholder)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(
            [tr("Name"), tr("Value"), tr("Formula"), tr("Access")])
        self.tree.currentItemChanged.connect(self._on_current)
        layout.addWidget(self.tree)

        self.form_host = QWidget()
        form = QFormLayout(self.form_host)
        self.name_edit = QLineEdit()
        self.label_edit = QLineEdit()
        self.type_combo = QComboBox()
        self.type_combo.addItems(TYPES)
        self.value_edit = QLineEdit()
        self.formula_edit = QLineEdit()
        self.access_combo = QComboBox()
        self.access_combo.addItems(ACCESS)
        self.options_edit = QLineEdit()
        self.options_edit.setPlaceholderText("Label=value; Label=value")
        for text, widget in ((tr("Name"), self.name_edit),
                             (tr("Label"), self.label_edit),
                             (tr("Type"), self.type_combo),
                             (tr("Value"), self.value_edit),
                             (tr("Formula"), self.formula_edit),
                             (tr("Access"), self.access_combo),
                             (tr("Options"), self.options_edit)):
            form.addRow(text, widget)
        row = QHBoxLayout()
        self.set_button = QPushButton(tr("Set attribute"))
        self.remove_button = QPushButton(tr("Remove attribute"))
        self.apply_button = QPushButton(tr("Apply"))
        for button in (self.set_button, self.remove_button, self.apply_button):
            row.addWidget(button)
        form.addRow(row)
        self.set_button.clicked.connect(self.set_attribute)
        self.remove_button.clicked.connect(self.remove_attribute)
        self.apply_button.clicked.connect(self.apply)
        layout.addWidget(self.form_host)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

    def _selected_instance(self):
        binding = _modules()[0]
        scene = self.app.scene
        picked = list(scene.selection)
        if len(picked) != 1 or not hasattr(picked[0], "ext"):
            return None
        group = picked[0]
        if not binding.is_dynamic(group):
            return None
        return group

    def refresh(self):
        group = self._selected_instance()
        if group is None:
            self._group = self._def_id = self._work = None
            self._dirty = False
            self._show(False)
            self.status.clear()
            return
        binding = _modules()[0]
        def_id = group.ext[KEY]["def"]
        if not (self._dirty and def_id == self._def_id):
            self._work = copy.deepcopy(binding.definition(self.app.scene, group))
            self._dirty = False
        self._group, self._def_id = group, def_id
        self._show(True)
        self._fill_tree()

    def _show(self, active):
        self.placeholder.setVisible(not active)
        self.tree.setVisible(active)
        self.form_host.setVisible(active)
        self.status.setVisible(active)
        if not active:
            self.tree.clear()

    def _current_value(self, node, name, attr):
        inst = self._group.ext.get(KEY, {})
        for source in (inst.get("last") or {}, inst.get("set") or {}):
            if name in source.get(node, {}):
                return source[node][name]
        return attr.get("value")

    def _fill_tree(self):
        keep = self._cursor()
        self.tree.blockSignals(True)
        self.tree.clear()
        for node, body in self._work["nodes"].items():
            title = self._work["name"] if node == "" else (body.get("label") or node)
            top = QTreeWidgetItem([title])
            top.setData(0, _NODE_ROLE, node)
            self.tree.addTopLevelItem(top)
            for name, attr in body.get("attrs", {}).items():
                child = QTreeWidgetItem([
                    attr.get("label") or name,
                    _text(self._current_value(node, name, attr)),
                    attr.get("formula") or "",
                    attr.get("access", "")])
                child.setData(0, _NODE_ROLE, node)
                child.setData(0, _ATTR_ROLE, name)
                top.addChild(child)
            top.setExpanded(True)
        self.tree.blockSignals(False)
        self._restore(keep)

    def _cursor(self):
        item = self.tree.currentItem()
        if item is None:
            return None
        return item.data(0, _NODE_ROLE), item.data(0, _ATTR_ROLE)

    def _restore(self, keep):
        if keep is None:
            return
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            if top.data(0, _NODE_ROLE) != keep[0]:
                continue
            if keep[1] is None:
                self.tree.setCurrentItem(top)
                return
            for j in range(top.childCount()):
                if top.child(j).data(0, _ATTR_ROLE) == keep[1]:
                    self.tree.setCurrentItem(top.child(j))
                    return
            self.tree.setCurrentItem(top)

    def _on_current(self, item, _previous):
        if item is None:
            return
        node, name = item.data(0, _NODE_ROLE), item.data(0, _ATTR_ROLE)
        if name is None:
            return
        attr = self._work["nodes"][node]["attrs"][name]
        self.name_edit.setText(name)
        self.label_edit.setText(attr.get("label") or "")
        self.type_combo.setCurrentText(attr.get("type", "string"))
        self.value_edit.setText(_text(attr.get("value")))
        self.formula_edit.setText(attr.get("formula") or "")
        self.access_combo.setCurrentText(attr.get("access", "none"))
        self.options_edit.setText(_format_options(attr.get("options")))

    def _target_node(self):
        cursor = self._cursor()
        return "" if cursor is None else cursor[0]

    def set_attribute(self):
        _, formula, spec = _modules()
        name = self.name_edit.text().strip().lower()
        if not name:
            self.status.setText(tr("The attribute needs a name."))
            return
        node = self._target_node()
        attrs = self._work["nodes"][node].setdefault("attrs", {})
        kind = self.type_combo.currentText()
        try:
            source = self.formula_edit.text().strip() or None
            if source:
                formula.parse(source)
            attr = dict(attrs.get(name, {}))
            attr.update(
                label=self.label_edit.text().strip() or name,
                type=kind,
                value=_convert(kind, self.value_edit.text())
                if self.value_edit.text().strip() else None,
                formula=source,
                access=self.access_combo.currentText())
            options = _parse_options(kind, self.options_edit.text())
            if options:
                attr["options"] = options
            else:
                attr.pop("options", None)
        except (spec.SpecError, formula.FormulaError, ValueError) as exc:
            self.status.setText(str(exc))
            return
        attrs[name] = attr
        self._dirty = True
        self.status.clear()
        self._fill_tree()

    def remove_attribute(self):
        cursor = self._cursor()
        if cursor is None or cursor[1] is None:
            return
        self._work["nodes"][cursor[0]]["attrs"].pop(cursor[1], None)
        self._dirty = True
        self._fill_tree()

    def apply(self):
        if self._work is None:
            return
        binding, formula, spec = _modules()
        group, def_id = self._group, self._def_id
        try:
            new_spec = spec.normalize(copy.deepcopy(self._work))
            binding.run(
                self.app.viewport,
                lambda s: binding.set_definition(s, def_id, new_spec),
                binding.instances_of(self.app.scene, def_id),
                tr("Edit dynamic attributes"))
        except Exception as exc:  # noqa: BLE001 - shown to the user, not raised from a slot
            self.status.setText(str(exc))
            return
        self._dirty = False
        self.status.clear()
        self._group = group
        self.refresh()
