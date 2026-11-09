"""Options: the user-facing attributes of the selected dynamic instance."""
from __future__ import annotations

import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFormLayout, QHBoxLayout, QLabel, QToolButton,
                               QVBoxLayout, QWidget)

from ..i18n import tr
from .common import (KEY, Lengths, ValueEditor, attr_label, error_label,
                     muted, node_title, same_value, value_text)


def _modules():
    from .. import binding, spec
    return binding, spec


class _Row:
    def __init__(self, node, name, attr, editor, view, reset, error):
        self.node, self.name, self.attr = node, name, attr
        self.editor, self.view, self.reset, self.error = editor, view, reset, error
        self.shown = None                      # the value the field shows now


class OptionsForm(QWidget):
    """One row per attribute users may edit or see. A change is applied at once
    (one undo step); the reset button drops the instance's own value."""

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.group = None
        self.status_text = ""
        self._rows: dict[tuple, _Row] = {}
        self._shape = None
        self._lengths = Lengths()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._host = QWidget()
        outer.addWidget(self._host)
        self.empty = muted(QLabel(tr(
            "No options for users yet. Open an attribute below and set "
            "“Users can edit” to show it here.")))
        self.empty.setWordWrap(True)
        outer.addWidget(self.empty)
        self.status = error_label()
        outer.addWidget(self.status)

    # ------------------------------------------------------------ building

    @staticmethod
    def _entries(spec_mod, definition):
        entries = list(spec_mod.editable_attrs(definition))
        for node, body in definition["nodes"].items():
            for name, attr in body.get("attrs", {}).items():
                if attr.get("access") == "view":
                    entries.append((node, name, attr))
        return entries

    def _shape_of(self, definition, entries):
        return json.dumps([[n, a, attr.get("label"), attr.get("type"),
                            attr.get("access"), attr.get("options"),
                            attr.get("min"), attr.get("max"),
                            node_title(definition, n)]
                           for n, a, attr in entries], default=str)

    def show_group(self, group, definition, result=None) -> None:
        _, spec_mod = _modules()
        self.group = group
        entries = self._entries(spec_mod, definition)
        shape = self._shape_of(definition, entries)
        if shape != self._shape or self._lengths_changed():
            self._rebuild(definition, entries)
            self._shape = shape
        self._update(result)

    def _lengths_changed(self) -> bool:
        now = Lengths()
        if (now.factor, now.suffix) != (self._lengths.factor, self._lengths.suffix):
            self._lengths = now
            return True
        return False

    def _rebuild(self, definition, entries):
        old = self._host
        self._host = QWidget()
        form = QFormLayout(self._host)
        form.setContentsMargins(0, 0, 0, 0)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.layout().replaceWidget(old, self._host)
        old.deleteLater()
        self._rows = {}
        for node, name, attr in entries:
            label = attr_label(name, attr)
            if node:
                label = f"{node_title(definition, node)}: {label}"
            field = QWidget()
            column = QVBoxLayout(field)
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(1)
            line = QHBoxLayout()
            line.setContentsMargins(0, 0, 0, 0)
            column.addLayout(line)
            editor = view = reset = None
            if attr.get("access") == "view":
                view = QLabel()
                view.setTextInteractionFlags(Qt.TextSelectableByMouse)
                line.addWidget(view, 1)
            else:
                editor = ValueEditor(
                    attr.get("type"), attr.get("value"), self._lengths, name=name,
                    options=attr.get("options"), minimum=attr.get("min"),
                    maximum=attr.get("max"), as_list=attr.get("access") == "list")
                line.addWidget(editor.widget, 1)
                reset = QToolButton()
                reset.setText("↺")
                reset.setFocusPolicy(Qt.NoFocus)    # Tab goes field to field
                reset.setAutoRaise(True)
                reset.setToolTip(tr("Back to the component's default"))
                line.addWidget(reset)
                key = (node, name)
                editor.changed.connect(lambda *_a, k=key: self._commit(k))
                reset.clicked.connect(lambda _c=False, k=key: self._reset(k))
            error = error_label()
            column.addWidget(error)
            caption = QLabel(label)
            caption.setWordWrap(True)
            form.addRow(caption, field)
            self._rows[(node, name)] = _Row(node, name, attr, editor, view, reset, error)
        self.empty.setVisible(not self._rows)

    # ------------------------------------------------------------- values

    def _current(self, node, name, attr):
        inst = (self.group.ext or {}).get(KEY, {}) if self.group is not None else {}
        for source in (inst.get("last") or {}, inst.get("set") or {}):
            if name in source.get(node, {}):
                return source[node][name]
        return attr.get("value")

    def _overridden(self, node, name) -> bool:
        inst = (self.group.ext or {}).get(KEY, {}) if self.group is not None else {}
        return name in (inst.get("set") or {}).get(node, {})

    def _update(self, result) -> None:
        errors = dict(getattr(result, "errors", None) or {})
        for key, row in self._rows.items():
            value = self._current(row.node, row.name, row.attr)
            row.shown = value
            if row.view is not None:
                row.view.setText(value_text(row.attr.get("type"), value,
                                            self._lengths, row.name))
            elif row.editor.widget.hasFocus() and same_value(row.editor.read(), value):
                pass                            # keep the cursor where it is
            else:
                row.editor.set(value)
            if row.reset is not None:
                row.reset.setVisible(self._overridden(row.node, row.name))
            message = errors.get(key, "")
            row.error.setText(message)
            row.error.setVisible(bool(message))
        self.status.setText(self.status_text)
        self.status.setVisible(bool(self.status_text))

    def changed_values(self) -> dict:
        changed = {}
        for (node, name), row in self._rows.items():
            if row.editor is None:
                continue
            now = row.editor.read()
            if not same_value(now, row.shown):
                changed.setdefault(node, {})[name] = now
        return changed

    def _run(self, values, label):
        binding, _ = _modules()
        group = self.group
        outcome = {}

        def mutate(scene):
            outcome["result"] = binding.set_values(scene, group, values)

        try:
            binding.run(self.app.viewport, mutate, [group], label)
        except Exception as exc:  # noqa: BLE001 - a Qt slot must not raise
            self.status_text = str(exc)
            self._update(None)
            return None
        self.status_text = ""
        result = outcome.get("result")
        self._update(result)
        return result

    def _commit(self, key) -> None:
        row = self._rows.get(key)
        if row is None or self.group is None:
            return
        now = row.editor.read()
        if same_value(now, row.shown):
            return
        self._run({key[0]: {key[1]: now}}, tr("Component options"))

    def _reset(self, key) -> None:
        if self.group is None:
            return
        self._run({key[0]: {key[1]: None}}, tr("Reset component option"))

    def apply(self) -> None:
        """Apply every field that differs from the model (one undo step)."""
        changed = self.changed_values()
        if changed and self.group is not None:
            self._run(changed, tr("Component options"))
