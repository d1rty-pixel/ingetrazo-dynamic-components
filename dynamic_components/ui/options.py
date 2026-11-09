"""Component Options dialog: the user-facing attributes of one dynamic instance."""
from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFormLayout, QLabel, QLineEdit,
                               QSpinBox, QVBoxLayout, QWidget)

from ..i18n import tr

KEY = "dynamic_components"
_BIG = 1.0e6


def _modules():
    from .. import binding, evaluate, spec
    return binding, evaluate, spec


class OptionsDialog(QDialog):
    def __init__(self, app, group, parent=None):
        super().__init__(parent)
        self.app = app
        self.group = group
        self._rows = {}
        self._errors = {}
        self._layout = QVBoxLayout(self)
        self._form_host = None
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.buttons = QDialogButtonBox()
        self.apply_button = self.buttons.addButton(
            tr("Apply"), QDialogButtonBox.ApplyRole)
        self.close_button = self.buttons.addButton(
            tr("Close"), QDialogButtonBox.RejectRole)
        self.apply_button.clicked.connect(self.apply)
        self.close_button.clicked.connect(self.close)
        self._layout.addWidget(self.status)
        self._layout.addWidget(self.buttons)
        self._build()

    def _build(self):
        binding, evaluate, spec = _modules()
        definition = binding.definition(self.app.scene, self.group)
        inst = self.group.ext.get(KEY, {})
        self._set = inst.get("set", {})
        self._last = inst.get("last") or {}
        self.setWindowTitle(
            tr("Component Options") + " — " + str(definition["name"]))
        if not self._errors:
            self._errors = self._evaluate_errors(evaluate, definition, inst)
        if self._form_host is not None:
            self._layout.removeWidget(self._form_host)
            self._form_host.deleteLater()
        host = QWidget()
        form = QFormLayout(host)
        self._rows = {}
        for node, name, attr in spec.editable_attrs(definition):
            self._add_row(form, definition, node, name, attr)
        for node, name, attr in self._view_attrs(definition):
            self._add_row(form, definition, node, name, attr)
        self._form_host = host
        self._layout.insertWidget(0, host)
        self.apply_button.setEnabled(bool(self._rows))

    @staticmethod
    def _evaluate_errors(evaluate, definition, inst):
        try:
            return dict(evaluate.evaluate(
                definition, inst.get("set", {}), inst.get("last")).errors)
        except Exception:
            return {}

    @staticmethod
    def _view_attrs(definition):
        for node, body in definition["nodes"].items():
            for name, attr in body.get("attrs", {}).items():
                if attr.get("access") == "view":
                    yield node, name, attr

    def _current(self, node, name, attr):
        for source in (self._last, self._set):
            if name in source.get(node, {}):
                return source[node][name]
        return attr.get("value")

    def _add_row(self, form, definition, node, name, attr):
        value = self._current(node, name, attr)
        label = attr.get("label") or name
        if node:
            part = definition["nodes"][node].get("label") or node
            label = f"{part}: {label}"
        if attr.get("access") == "view":
            widget = QLabel("" if value is None else str(value))
            read = None
        else:
            widget, read = self._editor(attr, value)
        box = QWidget()
        column = QVBoxLayout(box)
        column.setContentsMargins(0, 0, 0, 0)
        column.addWidget(widget)
        message = self._errors.get((node, name))
        if message:
            err = QLabel(message)
            err.setWordWrap(True)
            err.setStyleSheet("color: #c0392b;")
            err.setObjectName("error")
            column.addWidget(err)
        form.addRow(label, box)
        if read is not None:
            self._rows[(node, name)] = (read, read())

    def _editor(self, attr, value):
        kind = attr.get("type")
        if attr.get("access") == "list" or kind == "choice":
            combo = QComboBox()
            for text, data in attr.get("options") or []:
                combo.addItem(str(text), data)
            index = combo.findData(value)
            if index < 0 and value is not None:
                combo.addItem(str(value), value)
                index = combo.count() - 1
            combo.setCurrentIndex(max(index, 0))
            return combo, combo.currentData
        if kind in ("length", "float"):
            spin = QDoubleSpinBox()
            spin.setDecimals(3)
            spin.setRange(attr["min"] if attr.get("min") is not None else -_BIG,
                          attr["max"] if attr.get("max") is not None else _BIG)
            if kind == "length":
                spin.setSuffix(" m")
            spin.setValue(float(value or 0.0))
            return spin, spin.value
        if kind == "int":
            spin = QSpinBox()
            spin.setRange(int(attr["min"]) if attr.get("min") is not None
                          else -int(_BIG),
                          int(attr["max"]) if attr.get("max") is not None
                          else int(_BIG))
            spin.setValue(int(value or 0))
            return spin, spin.value
        if kind == "bool":
            check = QCheckBox()
            check.setChecked(bool(value))
            return check, check.isChecked
        edit = QLineEdit("" if value is None else str(value))
        return edit, edit.text

    def changed_values(self):
        changed = {}
        for (node, name), (read, initial) in self._rows.items():
            now = read()
            if now != initial:
                changed.setdefault(node, {})[name] = now
        return changed

    def apply(self):
        binding = _modules()[0]
        changed = self.changed_values()
        if not changed:
            return
        outcome = {}

        def mutate(scene):
            outcome["result"] = binding.set_values(scene, self.group, changed)

        try:
            binding.run(self.app.viewport, mutate, [self.group],
                        tr("Component options"))
        except Exception as exc:
            self.status.setText(str(exc))
            return
        self.status.clear()
        result = outcome.get("result")
        self._errors = dict(getattr(result, "errors", None) or {})
        self._build()
