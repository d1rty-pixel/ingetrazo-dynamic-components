"""Authoring: the attributes and formulas of the selected instance's definition."""
from __future__ import annotations

import copy
import json
import re

from PySide6.QtCore import QStringListModel, Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (QComboBox, QCompleter, QFormLayout, QFrame,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QMenu, QPushButton, QTableWidget,
                               QTableWidgetItem, QToolButton, QVBoxLayout,
                               QWidget)

from ..i18n import tr
from .common import (ACCESS_LABELS, ROOT_RESERVED, RESERVED_LABELS,
                     TYPE_LABELS, Fold, Lengths, ValueEditor, attr_label,
                     error_label, is_reserved, muted, narrow, node_title,
                     reference, scroll_safe, value_text)

KEY = "dynamic_components"

_RESERVED_TYPES = {
    "x": "length", "y": "length", "z": "length",
    "lenx": "length", "leny": "length", "lenz": "length",
    "rotx": "float", "roty": "float", "rotz": "float",
    "hidden": "bool", "material": "material", "copies": "int",
}
_NUMERIC = ("length", "float", "int")
_NAME_RE = re.compile(r"^[^\W\d]\w*$")
_TOKEN_RE = re.compile(r"[^\W\d][\w!]*$")
# Argument hints for the function picker; anything missing shows "value".
_HINTS = {
    "IF": "test, then, else", "CHOOSE": "index, value1, value2, …",
    "AND": "a, b, …", "OR": "a, b, …", "NOT": "value",
    "MIN": "a, b, …", "MAX": "a, b, …", "ROUND": "number, decimals",
    "FLOOR": "number, step", "CEILING": "number, step", "PI": "",
    "LEFT": "text, count", "RIGHT": "text, count", "MID": "text, start, count",
    "CONCATENATE": "text1, text2, …", "LEN": "text",
}


def _modules():
    from .. import binding, evaluate, formula, spec
    return binding, evaluate, formula, spec


def slug(text: str) -> str:
    """An attribute name from a label: ``Plattenstärke`` → ``plattenstaerke``."""
    text = text.strip().lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(a, b)
    text = re.sub(r"\W+", "_", text).strip("_")
    if not text or text[0].isdigit():
        text = "a_" + text
    return text


def _fingerprint(definition) -> str:
    return json.dumps(definition, sort_keys=True, default=str)


def _shape(work) -> str:
    return json.dumps({n: list(b.get("attrs", {})) for n, b in work["nodes"].items()})


# ------------------------------------------------------------------ widgets

class ElidedLabel(QLabel):
    """One line that ends in … when the tray is too narrow; full text as tip."""

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._full = ""
        self.setMinimumWidth(10)
        self.set_full(text)

    def set_full(self, text: str) -> None:
        self._full = text or ""
        self.setToolTip(self._full)
        self._elide()

    def full(self) -> str:
        return self._full

    def resizeEvent(self, event):  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._elide()

    def _elide(self):
        metrics = QFontMetrics(self.font())
        super().setText(metrics.elidedText(self._full, Qt.ElideRight,
                                           max(10, self.width())))


class FormulaEdit(QLineEdit):
    """A formula field that completes the word at the cursor (references and
    functions) instead of the whole line."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText(tr("No formula: the default value is used"))
        self._model = QStringListModel()
        self._completer = QCompleter(self._model, self)
        self._completer.setWidget(self)
        self._completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._completer.setCompletionMode(QCompleter.PopupCompletion)
        self._completer.activated[str].connect(self._complete_with)
        self.textEdited.connect(self._suggest)
        self.setStyleSheet("font-family: monospace;")

    def set_words(self, words) -> None:
        self._model.setStringList(sorted(set(words), key=str.lower))

    def _token(self) -> str:
        before = self.text()[: self.cursorPosition()]
        match = _TOKEN_RE.search(before)
        return match.group(0) if match else ""

    def _suggest(self, _text=None) -> None:
        token = self._token()
        popup = self._completer.popup()
        if not token:
            popup.hide()
            return
        self._completer.setCompletionPrefix(token)
        if self._completer.completionCount() == 0:
            popup.hide()
            return
        if (self._completer.completionCount() == 1
                and self._completer.currentCompletion().lower() == token.lower()):
            popup.hide()
            return
        rect = self.cursorRect()
        rect.setWidth(max(220, popup.sizeHintForColumn(0) + 24))
        self._completer.complete(rect)

    def _complete_with(self, word: str) -> None:
        token = self._token()
        pos = self.cursorPosition()
        text = self.text()
        start = pos - len(token)
        self.setText(text[:start] + word + text[pos:])
        self.setCursorPosition(start + len(word))
        self.textEdited.emit(self.text())

    def insert_text(self, text: str, cursor_back: int = 0) -> None:
        if not self.text().strip():
            self.setText("=")
            self.setCursorPosition(1)
        self.insert(text)
        if cursor_back:
            self.setCursorPosition(self.cursorPosition() - cursor_back)
        self.setFocus()
        self.textEdited.emit(self.text())


class OptionsTable(QWidget):
    """The choices of a list: label and value per row, + and − to edit."""

    def __init__(self, kind, options, lengths, on_change, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.lengths = lengths
        self._on_change = on_change
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        self.table = QTableWidget(0, 2)
        unit = lengths.suffix.strip() if kind == "length" else ""
        self.table.setHorizontalHeaderLabels(
            [tr("Shown as"), tr("Value") + (f" ({unit})" if unit else "")])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setMinimumHeight(90)
        lay.addWidget(self.table)
        buttons = QHBoxLayout()
        self.add_button = QToolButton()
        self.add_button.setText("+")
        self.add_button.setToolTip(tr("Add a choice"))
        self.remove_button = QToolButton()
        self.remove_button.setText("−")
        self.remove_button.setToolTip(tr("Remove the selected choice"))
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.remove_button)
        buttons.addStretch(1)
        lay.addLayout(buttons)
        for label, value in options or []:
            self._append(str(label), self._value_text(value))
        self._fit()
        self.add_button.clicked.connect(self._add)
        self.remove_button.clicked.connect(self._remove)
        self.table.itemChanged.connect(lambda _i: self._on_change())

    def _value_text(self, value) -> str:
        if self.kind == "length" and isinstance(value, (int, float)):
            return self.lengths.number_text(value)
        if isinstance(value, bool):
            return tr("Yes") if value else tr("No")
        if isinstance(value, float):
            return f"{value:g}"
        return "" if value is None else str(value)

    def _append(self, label, value_text):
        self.table.blockSignals(True)
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(label))
        self.table.setItem(row, 1, QTableWidgetItem(value_text))
        self.table.blockSignals(False)

    def _fit(self):
        rows = self.table.rowCount()
        height = self.table.horizontalHeader().height() + 6 + sum(
            self.table.rowHeight(r) for r in range(rows))
        self.table.setFixedHeight(max(90, min(height, 240)))

    def _add(self):
        self._append("", "")
        self._fit()
        row = self.table.rowCount() - 1
        self.table.setCurrentCell(row, 0)
        self.table.editItem(self.table.item(row, 0))

    def _remove(self):
        row = self.table.currentRow()
        if row < 0:
            row = self.table.rowCount() - 1
        if row >= 0:
            self.table.removeRow(row)
            self._fit()
            self._on_change()

    def _parse(self, text: str):
        text = text.strip()
        if self.kind == "length":
            return self.lengths.parse(text)
        if self.kind == "float":
            return float(text.replace(",", "."))
        if self.kind == "int":
            return int(float(text.replace(",", ".")))
        if self.kind == "bool":
            return text.lower() in ("1", "true", "yes", "ja", "on", tr("Yes").lower())
        return text

    def options(self) -> list:
        """[[label, value], …]; a row without a value is skipped. Raises
        ValueError naming the row whose value cannot be read."""
        result = []
        for row in range(self.table.rowCount()):
            label = (self.table.item(row, 0) or QTableWidgetItem()).text().strip()
            raw = (self.table.item(row, 1) or QTableWidgetItem()).text()
            if not raw.strip():
                continue
            try:
                value = self._parse(raw)
            except ValueError:
                raise ValueError(tr("Choice {n}: “{v}” is not a valid value")
                                 .replace("{n}", str(row + 1)).replace("{v}", raw)) from None
            result.append([label or raw.strip(), value])
        return result


class _AttrRow(QFrame):
    def __init__(self, owner, node, name, parent=None):
        super().__init__(parent)
        self.owner, self.node, self.name = owner, node, name
        self.setObjectName("attrRow")
        self.setCursor(Qt.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 3, 6, 3)
        lay.setSpacing(0)
        top = QHBoxLayout()
        top.setSpacing(6)
        self.title = QLabel()
        self.value = QLabel()
        self.value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        top.addWidget(self.title, 1)
        top.addWidget(self.value)
        lay.addLayout(top)
        self.detail = muted(ElidedLabel(), small=True, mono=True)
        lay.addWidget(self.detail)
        self.error = error_label()
        lay.addWidget(self.error)
        self.set_selected(False)

    def set_selected(self, on: bool) -> None:
        self.setStyleSheet(
            "QFrame#attrRow { border-radius: 4px; %s }"
            "QFrame#attrRow:hover { background: palette(midlight); }"
            % ("background: palette(alternate-base); "
               "border-left: 3px solid palette(highlight);" if on else ""))

    def mousePressEvent(self, event):  # noqa: N802 - Qt override
        if event.button() == Qt.LeftButton:
            self.owner.select(self.node, self.name)
        super().mousePressEvent(event)


# ------------------------------------------------------------------- editor

class AttributesEditor(QWidget):
    """Fold sections per node; rows open an inline editor; Apply writes the
    definition (one undo step for every instance of it)."""

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.group = None
        self.def_id = None
        self.inst = {}
        self.work = None
        self.dirty = False
        self.current = None              # (node, name) with the editor open
        self._new = set()                # added since the last Apply: name editable
        self._open = {}                  # (def_id, node) -> folded open
        self._rows = {}                  # (node, name) -> _AttrRow
        self._folds = {}                 # node -> Fold
        self._card = None
        self._shape = None
        self._result = None
        self.lengths = Lengths()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)
        self._sections = QWidget()
        self._sections_layout = QVBoxLayout(self._sections)
        self._sections_layout.setContentsMargins(0, 0, 0, 0)
        self._sections_layout.setSpacing(10)
        outer.addWidget(self._sections)

        self.status = error_label()
        outer.addWidget(self.status)
        self._known = None               # the definition as last seen or written

    # ------------------------------------------------------------- input

    def show_group(self, group, definition, inst, present=None) -> None:
        self._present = None if present is None else set(present) | {""}
        def_id = (inst or {}).get("def")
        known = _fingerprint(definition)
        reopen = False
        if def_id != self.def_id:
            self.work = copy.deepcopy(definition)
            self.dirty = False
            self._new.clear()
            self.current = None
        elif known != self._known:
            # Changed by something else (undo, redo, another instance's tab):
            # what is shown follows it; a pending broken formula is dropped.
            self.work = copy.deepcopy(definition)
            self.dirty = False
            reopen = self._card is not None
        self._known = known
        self.group, self.def_id, self.inst = group, def_id, inst or {}
        lengths = Lengths()
        force = (lengths.factor, lengths.suffix) != (self.lengths.factor,
                                                      self.lengths.suffix)
        self.lengths = lengths
        self._render(force=force)
        if reopen and self.current in self._rows and self._card is not None:
            self._open_card(*self.current)
            self._refresh_texts()

    def clear(self) -> None:
        self.group = self.def_id = self.work = self._known = None
        self.inst = {}
        self.dirty = False
        self.current = None
        self._new.clear()
        self._rebuild()

    # ------------------------------------------------------------ helpers

    def _attrs(self, node) -> dict:
        return self.work["nodes"][node].setdefault("attrs", {})

    def _evaluate(self):
        _, evaluate, _, spec = _modules()
        try:
            normalized = spec.normalize(copy.deepcopy(self.work))
            return evaluate.evaluate(normalized,
                                     copy.deepcopy(self.inst.get("set") or {}),
                                     self.inst.get("last")), ""
        except Exception as exc:  # noqa: BLE001 - shown, never raised
            return None, str(exc)

    def _render(self, force=False) -> None:
        if self.work is None:
            self._rebuild()
            return
        shape = _shape(self.work) + repr(sorted(getattr(self, "_present", None) or ()))
        if force or shape != self._shape:
            self._rebuild()
            self._shape = shape
        self._refresh_texts()

    def _rebuild(self) -> None:
        while self._sections_layout.count():
            item = self._sections_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self._rows, self._folds, self._card = {}, {}, None
        if self.work is None:
            self._shape = None
            return
        for node, body in self.work["nodes"].items():
            if not self._shows(node):
                continue                 # deleted from this instance
            fold = Fold(self._fold_title(node), self._open.get((self.def_id, node), False),
                        on_toggle=lambda on, n=node: self._open.__setitem__(
                            (self.def_id, n), on))
            column = QVBoxLayout(fold.body)
            column.setContentsMargins(4, 4, 4, 4)
            column.setSpacing(2)
            for name in body.get("attrs", {}):
                row = _AttrRow(self, node, name)
                column.addWidget(row)
                self._rows[(node, name)] = row
            add = QToolButton()
            add.setText("+ " + tr("Add property"))
            add.setPopupMode(QToolButton.InstantPopup)
            add.setAutoRaise(True)
            add.setMenu(self._add_menu(node, add))
            column.addWidget(add, 0, Qt.AlignLeft)
            self._sections_layout.addWidget(fold)
            self._folds[node] = fold
        if self.current in self._rows:
            self._open_card(*self.current)
        else:
            self.current = None

    def _shows(self, node) -> bool:
        present = getattr(self, "_present", None)
        return present is None or node in present

    def _fold_title(self, node) -> str:
        count = len(self.work["nodes"][node].get("attrs", {}))
        title = node_title(self.work, node)
        prefix = tr("Attributes") if node == "" else tr("Part")
        return f"{prefix}: {title}  ({count})"

    def _refresh_texts(self) -> None:
        result, problem = self._evaluate()
        self._result = result
        values = getattr(result, "values", {}) or {}
        errors = dict(getattr(result, "errors", {}) or {})
        for (node, name), row in self._rows.items():
            attr = self._attrs(node).get(name, {})
            row.title.setText(attr_label(name, attr))
            value = values.get(node, {}).get(name, attr.get("value"))
            row.value.setText(value_text(attr.get("type"), value, self.lengths, name))
            if attr.get("formula"):
                row.detail.set_full(attr["formula"])
                muted(row.detail, small=True, mono=True)
            elif attr.get("access") in ("textbox", "list"):
                row.detail.set_full(tr("Option for users"))
                muted(row.detail, small=True)
            else:
                row.detail.set_full("")
            row.detail.setVisible(bool(row.detail.full()))
            message = errors.get((node, name), "")
            row.error.setText(message)
            row.error.setVisible(bool(message))
            row.set_selected((node, name) == self.current)
        for node, fold in self._folds.items():
            fold.set_title(self._fold_title(node))
        if self._card is not None:
            self._card.update_preview(values, errors)
        self.status.setText(problem)
        self.status.setVisible(bool(problem))

    def _changed(self, apply=True) -> None:
        """The working copy changed. ``apply``: a finished edit (a field left,
        a choice made, an attribute added or removed) goes into the
        definition at once, one undo step; while typing only the preview
        follows."""
        self._render()
        if apply:
            self.apply()

    # ------------------------------------------------------------ actions

    def select(self, node, name) -> None:
        if self.current == (node, name):
            self.current = None
            self._close_card()
        else:
            self.current = (node, name)
            self._open_card(node, name)
        self._refresh_texts()

    def _close_card(self) -> None:
        if self._card is not None:
            self._card.hide()
            self._card.deleteLater()
            self._card = None

    def _open_card(self, node, name) -> None:
        self._close_card()
        row = self._rows.get((node, name))
        fold = self._folds.get(node)
        if row is None or fold is None:
            return
        fold.set_open(True)
        column = fold.body.layout()
        self._card = _Card(self, node, name)
        column.insertWidget(column.indexOf(row) + 1, self._card)

    def _add_menu(self, node, button) -> QMenu:
        menu = QMenu(button)

        def fill():
            menu.clear()
            have = self._attrs(node)
            offered = ROOT_RESERVED if node == "" else tuple(RESERVED_LABELS)
            for name in offered:
                if name not in have:
                    menu.addAction(tr(RESERVED_LABELS[name]),
                                   lambda n=name: self.add_attribute(node, n))
            if menu.actions():
                menu.addSeparator()
            menu.addAction(tr("Custom attribute…"),
                           lambda: self.add_attribute(node, None))
        menu.aboutToShow.connect(fill)
        return menu

    def _rest_value(self, node, name):
        rest = self.work["nodes"][node].get("rest", {})
        axes = {"x": 0, "y": 1, "z": 2}
        if name.startswith("len") and name[3:] in axes and "size" in rest:
            return float(rest["size"][axes[name[3:]]])
        if name in axes and "xform" in rest:
            return float(rest["xform"][12 + axes[name]])
        return None

    def add_attribute(self, node, name) -> None:
        attrs = self._attrs(node)
        if name is None:
            base, n = "attribute", 2
            name = base
            while name in attrs or is_reserved(name) or name == "copy":
                name, n = f"{base}{n}", n + 1
            attrs[name] = {"label": tr("New attribute"), "type": "length",
                           "value": 0.0, "formula": None, "access": "none"}
            self._new.add((node, name))
        else:
            kind = _RESERVED_TYPES[name]
            value = self._rest_value(node, name)
            if value is None and not (node == "" and name in ROOT_RESERVED):
                value = {"bool": False, "int": 0, "material": ""}.get(kind, 0.0)
            attrs[name] = {"label": tr(RESERVED_LABELS[name]), "type": kind,
                           "value": value, "formula": None, "access": "none"}
        self.current = (node, name)
        self._open[(self.def_id, node)] = True
        self._changed()

    def remove_attribute(self, node, name) -> None:
        self._attrs(node).pop(name, None)
        self._new.discard((node, name))
        if self.current == (node, name):
            self.current = None
        self._changed()

    def rename(self, node, old, new) -> str:
        """Rename an attribute added since the last Apply; '' or an error."""
        new = new.strip().lower()
        _, _, formula, _ = _modules()
        if new == old:
            return ""
        if not _NAME_RE.match(new):
            return tr("A name starts with a letter and has only letters, digits and _.")
        if is_reserved(new) or new == "copy":
            return tr("“{n}” is reserved; pick it from “Add property”.").replace("{n}", new)
        attrs = self._attrs(node)
        if new in attrs:
            return tr("“{n}” already exists here.").replace("{n}", new)
        self.work["nodes"][node]["attrs"] = {(new if k == old else k): v
                                             for k, v in attrs.items()}
        self._new.discard((node, old))
        self._new.add((node, new))
        if self.current == (node, old):
            self.current = (node, new)
        # In place: rebuilding would destroy the field the user tabbed to.
        row = self._rows.pop((node, old), None)
        if row is not None:
            row.name = new
            self._rows[(node, new)] = row
        if self._card is not None and (self._card.node, self._card.name) == (node, old):
            self._card.name = new
        self._shape = _shape(self.work) + repr(sorted(getattr(self, "_present", None) or ()))
        self._changed()
        return ""

    def discard(self) -> None:
        """Drop a pending edit that could not be applied (a broken formula)."""
        if self.group is None:
            return
        binding = _modules()[0]
        definition = binding.definition(self.app.scene, self.group)
        if definition is not None:
            self.work = copy.deepcopy(definition)
            self._known = _fingerprint(definition)
        self.dirty = False
        if self.current and self.current[1] not in self._attrs(self.current[0]):
            self.current = None
        self._shape = None
        self._render()

    def apply(self) -> bool:
        """Write the working copy into the definition (one undo step). A
        formula that does not parse holds everything back until it does."""
        if self.work is None:
            return False
        binding, _, formula, spec = _modules()
        for node, body in self.work["nodes"].items():
            for name, attr in body.get("attrs", {}).items():
                if not attr.get("formula"):
                    continue
                try:
                    formula.parse(attr["formula"])
                except formula.FormulaError as exc:
                    self.dirty = True
                    self.status.setText(
                        tr("Not applied yet — fix the formula of {a}: {e}")
                        .replace("{a}", f"{node_title(self.work, node)} › "
                                        f"{attr_label(name, attr)}")
                        .replace("{e}", str(exc)))
                    self.status.setVisible(True)
                    return False
        def_id = self.def_id
        previous = self._known
        try:
            new_spec = spec.normalize(copy.deepcopy(self.work))
            known = _fingerprint(new_spec)
            if known == previous:
                self.dirty = False
                return True                      # nothing new to write
            # Set first: the document hook refreshes this editor while the
            # command runs, and must see its own write, not a stranger's.
            self._known = known
            binding.run(self.app.viewport,
                        lambda s: binding.set_definition(s, def_id, new_spec),
                        binding.instances_of(self.app.scene, def_id),
                        tr("Edit dynamic attributes"))
        except Exception as exc:  # noqa: BLE001 - shown to the user
            self._known = previous
            self.dirty = True
            self.status.setText(str(exc))
            self.status.setVisible(True)
            return False
        self.dirty = False
        self._refresh_texts()
        return True

    # --------------------------------------------------- formula vocabulary

    def references(self, node):
        """(menu path, inserted text) for every value a formula on ``node``
        may read, in the order the insert menu lists them."""
        out = []
        if node != "":
            for name, attr in self._attrs(node).items():
                out.append(((tr("This part"), attr_label(name, attr)), name))
            out.append(((tr("This part"), tr("Copy number (0 = original)")), "copy"))
        root = self._attrs("")
        names = list(root) + [n for n in ROOT_RESERVED if n not in root]
        for name in names:
            attr = root.get(name, {"label": tr(RESERVED_LABELS.get(name, name))})
            out.append(((tr("Component"), attr_label(name, attr)),
                        reference(node, "", name)))
        for other, body in self.work["nodes"].items():
            if other in ("", node) or not self._shows(other):
                continue
            for name, attr in body.get("attrs", {}).items():
                out.append(((tr("Other parts"), node_title(self.work, other),
                             attr_label(name, attr)), reference(node, other, name)))
        return out


class _Card(QFrame):
    """The inline editor of one attribute, right under its row."""

    def __init__(self, owner: AttributesEditor, node, name, parent=None):
        super().__init__(parent)
        self.owner, self.node, self.name = owner, node, name
        self.setObjectName("attrCard")
        self.setStyleSheet("QFrame#attrCard { border: 1px solid palette(mid); "
                           "border-radius: 4px; background: palette(base); }")
        attr = owner._attrs(node)[name]
        reserved = is_reserved(name)
        self._name_touched = False
        form = QFormLayout(self)
        form.setContentsMargins(8, 8, 8, 8)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.form = form

        self.label_edit = narrow(QLineEdit(attr_label(name, attr)))
        form.addRow(tr("Label"), self.label_edit)
        self.label_edit.editingFinished.connect(self._label_done)
        self.label_edit.textEdited.connect(self._label_typed)

        self.name_error = error_label()
        if (node, name) in owner._new:
            self.name_edit = narrow(QLineEdit(name))
            self.name_edit.setStyleSheet("font-family: monospace;")
            self.name_edit.textEdited.connect(lambda _t: setattr(self, "_name_touched", True))
            self.name_edit.editingFinished.connect(self._name_done)
            form.addRow(tr("Name in formulas"), self.name_edit)
            form.addRow("", self.name_error)
        else:
            self.name_edit = None
            used = reference(node, "", name) if node == "" else name
            shown = muted(QLabel(used), mono=True)
            shown.setTextInteractionFlags(Qt.TextSelectableByMouse)
            shown.setToolTip(tr("Parts read it as {r}").replace(
                "{r}", reference("part", node, name)) if node == "" else
                tr("Other parts read it as {r}").replace("{r}", f"{node}!{name}"))
            form.addRow(tr("Name in formulas"), shown)

        self.type_combo = None
        if not reserved:
            self.type_combo = scroll_safe(narrow(QComboBox()))
            for kind, label in TYPE_LABELS.items():
                self.type_combo.addItem(tr(label), kind)
            self.type_combo.setCurrentIndex(max(0, self.type_combo.findData(attr["type"])))
            self.type_combo.currentIndexChanged.connect(self._type_changed)
            form.addRow(tr("Type"), self.type_combo)

        self._value_host = QWidget()
        QVBoxLayout(self._value_host).setContentsMargins(0, 0, 0, 0)
        self._value_label = QLabel()
        form.addRow(self._value_label, self._value_host)
        self._value_editor = None
        self._build_value_editor()

        formula_row = QWidget()
        formula_line = QHBoxLayout(formula_row)
        formula_line.setContentsMargins(0, 0, 0, 0)
        formula_line.setSpacing(2)
        self.formula_edit = FormulaEdit()
        narrow(self.formula_edit)
        self.formula_edit.setText(attr.get("formula") or "")
        self.insert_button = QToolButton()
        self.insert_button.setFocusPolicy(Qt.NoFocus)   # Tab goes field to field
        self.insert_button.setText("+")
        self.insert_button.setToolTip(tr("Insert a value or a function"))
        self.insert_button.setPopupMode(QToolButton.InstantPopup)
        self.insert_menu = QMenu(self.insert_button)
        self.insert_menu.aboutToShow.connect(self._fill_insert_menu)
        self.insert_button.setMenu(self.insert_menu)
        formula_line.addWidget(self.formula_edit, 1)
        formula_line.addWidget(self.insert_button)
        form.addRow(tr("Formula"), formula_row)
        self.preview = QLabel()
        self.preview.setWordWrap(True)
        form.addRow("", self.preview)
        self.formula_edit.textEdited.connect(self._formula_typed)
        self.formula_edit.editingFinished.connect(self._formula_done)
        self.formula_edit.set_words(self._words())

        self.access_combo = scroll_safe(narrow(QComboBox()))
        for access, label in ACCESS_LABELS.items():
            self.access_combo.addItem(tr(label), access)
        self.access_combo.setCurrentIndex(
            max(0, self.access_combo.findData(attr.get("access", "none"))))
        self.access_combo.currentIndexChanged.connect(self._access_changed)
        form.addRow(tr("Users"), self.access_combo)

        self.limits = QWidget()
        limits = QHBoxLayout(self.limits)
        limits.setContentsMargins(0, 0, 0, 0)
        self.min_edit = narrow(QLineEdit())
        self.max_edit = narrow(QLineEdit())
        for edit, key, hint in ((self.min_edit, "min", tr("no minimum")),
                                (self.max_edit, "max", tr("no maximum"))):
            edit.setPlaceholderText(hint)
            edit.editingFinished.connect(lambda k=key, e=edit: self._limit_done(k, e))
            limits.addWidget(edit)
        self._limits_label = QLabel(tr("Limits"))
        form.addRow(self._limits_label, self.limits)
        self.limit_error = error_label()
        form.addRow("", self.limit_error)

        self._options_host = QWidget()
        QVBoxLayout(self._options_host).setContentsMargins(0, 0, 0, 0)
        self._options_label = QLabel(tr("Choices"))
        form.addRow(self._options_label, self._options_host)
        self.options_error = error_label()
        form.addRow("", self.options_error)
        self.options_table = None

        bottom = QHBoxLayout()
        self.remove_button = QPushButton(tr("Remove"))
        self.remove_button.setToolTip(tr("Remove this attribute from the definition"))
        self.done_button = QPushButton(tr("Done"))
        bottom.addWidget(self.remove_button)
        bottom.addStretch(1)
        bottom.addWidget(self.done_button)
        form.addRow(bottom)
        self.remove_button.clicked.connect(
            lambda: owner.remove_attribute(self.node, self.name))
        self.done_button.setToolTip(tr("Close the editor; changes are applied as you go."))
        self.done_button.clicked.connect(lambda: owner.select(self.node, self.name))
        self._sync_kind_parts()

    # ----------------------------------------------------------- state

    @property
    def attr(self) -> dict:
        return self.owner._attrs(self.node)[self.name]

    def _kind(self) -> str:
        return self.attr.get("type", "length")

    def _words(self):
        words = [text for _path, text in self.owner.references(self.node)]
        _, _, formula, _ = _modules()
        words += [f + "(" for f in getattr(formula, "FUNCTIONS", ())]
        return words

    def _build_value_editor(self) -> None:
        lay = self._value_host.layout()
        while lay.count():
            item = lay.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        attr = self.attr
        value = attr.get("value")
        if value is None and self.node == "" and self.name in ROOT_RESERVED:
            value = self.owner._rest_value("", self.name)
            if value is None:
                size = self.owner.work["nodes"][""].get("rest", {}).get("size")
                value = size[ROOT_RESERVED.index(self.name)] if size else 0.0
        self._value_editor = ValueEditor(
            attr.get("type"), value, self.owner.lengths, name=self.name,
            options=attr.get("options"), minimum=None, maximum=None,
            as_list=attr.get("type") == "choice")
        self._value_editor.changed.connect(lambda *_a: self._value_done())
        lay.addWidget(self._value_editor.widget)
        if hasattr(self, "done_button"):
            self.fix_tab_order()

    def fix_tab_order(self) -> None:
        """Field to field in reading order. Qt chains widgets in the order they
        were made, and the value field and the choices table are made again
        when the type or the access changes."""
        chain = [self.label_edit, self.name_edit, self.type_combo,
                 self._value_editor.widget if self._value_editor else None,
                 self.formula_edit, self.access_combo, self.min_edit,
                 self.max_edit,
                 self.options_table.table if self.options_table else None,
                 self.options_table.add_button if self.options_table else None,
                 self.options_table.remove_button if self.options_table else None,
                 self.remove_button, self.done_button]
        chain = [w for w in chain if w is not None]
        for a, b in zip(chain, chain[1:]):
            QWidget.setTabOrder(a, b)

    def _sync_kind_parts(self) -> None:
        kind = self._kind()
        attr = self.attr
        numeric = kind in _NUMERIC
        self.limits.setVisible(numeric)
        self._limits_label.setVisible(numeric)
        if numeric:
            for edit, key in ((self.min_edit, "min"), (self.max_edit, "max")):
                bound = attr.get(key)
                if bound is None:
                    edit.setText("")
                elif kind == "length":
                    edit.setText(self.owner.lengths.number_text(bound))
                else:
                    edit.setText(f"{bound:g}")
                unit = self.owner.lengths.suffix.strip() if kind == "length" else ""
                edit.setPlaceholderText(
                    (tr("no minimum") if key == "min" else tr("no maximum"))
                    + (f" ({unit})" if unit else ""))
        wants_options = kind == "choice" or attr.get("access") == "list"
        self._options_label.setVisible(wants_options)
        self._options_host.setVisible(wants_options)
        lay = self._options_host.layout()
        while lay.count():
            item = lay.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self.options_table = None
        if wants_options:
            self.options_table = OptionsTable(kind, attr.get("options"),
                                              self.owner.lengths, self._options_done)
            lay.addWidget(self.options_table)
        if hasattr(self, "done_button"):
            self.fix_tab_order()

    def update_preview(self, values, errors) -> None:
        if self.name not in self.owner._attrs(self.node):
            return
        attr = self.attr
        if attr.get("formula"):
            self._value_label.setText(tr("Fallback value"))
            self._value_label.setToolTip(tr(
                "Used only while the formula cannot be evaluated."))
        else:
            self._value_label.setText(tr("Value"))
            self._value_label.setToolTip("")
        message = errors.get((self.node, self.name))
        if not attr.get("formula"):
            self.preview.setText("")
            self.preview.setVisible(False)
            return
        self.preview.setVisible(True)
        if message:
            self.preview.setStyleSheet("color: #c0392b;")
            self.preview.setText("✗ " + message)
            return
        value = values.get(self.node, {}).get(self.name)
        self.preview.setStyleSheet("color: #2e8b57;")
        self.preview.setText("✓ " + tr("gives {v}").replace(
            "{v}", value_text(attr.get("type"), value, self.owner.lengths, self.name)))

    # -------------------------------------------------------- handlers

    def _label_typed(self, text) -> None:
        if self.name_edit is not None and not self._name_touched:
            self.name_edit.setText(slug(text) if text.strip() else self.name)

    def _label_done(self) -> None:
        text = self.label_edit.text().strip()
        changed = bool(text) and text != self.attr.get("label")
        if changed:
            self.attr["label"] = text
        if self.name_edit is not None and not self._name_touched \
                and self.name_edit.text().strip().lower() != self.name:
            if self._name_done() and changed:
                self.owner._changed()    # rename refused: the label still counts
        elif changed:
            self.owner._changed()

    def _name_done(self) -> str:
        """Rename to what the name field says; returns the problem, if any
        (on success the editor re-renders and this card is replaced)."""
        if self.name_edit is None:
            return ""
        problem = self.owner.rename(self.node, self.name, self.name_edit.text())
        self.name_error.setText(problem)
        self.name_error.setVisible(bool(problem))
        return problem

    def _type_changed(self) -> None:
        _, _, _, spec = _modules()
        kind = self.type_combo.currentData()
        attr = self.attr
        attr["type"] = kind
        trial = {"type": kind}
        try:
            attr["value"] = spec.coerce(trial, attr.get("value"))
        except Exception:  # noqa: BLE001 - not convertible: the type's default
            attr["value"] = {"bool": False, "int": 0, "string": "", "material": "",
                             "choice": ""}.get(kind, 0.0)
        if kind not in _NUMERIC:
            attr.pop("min", None)
            attr.pop("max", None)
        self._build_value_editor()
        self._sync_kind_parts()
        self.owner._changed()

    def _value_done(self) -> None:
        value = self._value_editor.read()
        if value != self.attr.get("value"):
            self.attr["value"] = value
            self.owner._changed()

    def _formula_typed(self, text) -> None:
        _, _, formula, _ = _modules()
        source = text.strip() or None
        self.attr["formula"] = source
        if source:
            try:
                formula.parse(source)
            except formula.FormulaError as exc:
                self.preview.setVisible(True)
                self.preview.setStyleSheet("color: #c0392b;")
                self.preview.setText("✗ " + str(exc))
                self.owner.dirty = True
                return
        self.owner._changed(apply=False)     # preview only; applied on leaving

    def _formula_done(self) -> None:
        if self.name in self.owner._attrs(self.node):
            self.owner._changed()

    def _access_changed(self) -> None:
        self.attr["access"] = self.access_combo.currentData()
        self._sync_kind_parts()
        self.owner._changed()

    def _limit_done(self, key, edit) -> None:
        text = edit.text().strip()
        try:
            if not text:
                value = None
            elif self._kind() == "length":
                value = self.owner.lengths.parse(text)
            else:
                value = float(text.replace(",", "."))
        except ValueError:
            self.limit_error.setText(tr("“{t}” is not a number").replace("{t}", text))
            self.limit_error.setVisible(True)
            return
        self.limit_error.setVisible(False)
        other = self.attr.get("max" if key == "min" else "min")
        if value is not None and other is not None and (
                (key == "min" and value > other) or (key == "max" and value < other)):
            self.limit_error.setText(tr("The minimum must not be above the maximum."))
            self.limit_error.setVisible(True)
            return
        if value is None:
            self.attr.pop(key, None)
        else:
            self.attr[key] = value
        self.owner._changed()

    def _options_done(self) -> None:
        try:
            options = self.options_table.options()
        except ValueError as exc:
            self.options_error.setText(str(exc))
            self.options_error.setVisible(True)
            return
        self.options_error.setVisible(False)
        if options:
            self.attr["options"] = options
        else:
            self.attr.pop("options", None)
        if self._kind() == "choice":
            self._build_value_editor()
        self.owner._changed()

    def _fill_insert_menu(self) -> None:
        menu = self.insert_menu
        menu.clear()
        submenus = {}

        def submenu(path):
            parent = menu
            for depth in range(1, len(path)):
                key = path[:depth]
                if key not in submenus:
                    submenus[key] = parent.addMenu(key[-1])
                parent = submenus[key]
            return parent

        for path, text in self.owner.references(self.node):
            action = submenu(path).addAction(f"{path[-1]}    {text}")
            action.triggered.connect(lambda _c=False, t=text: self.formula_edit.insert_text(t))
        menu.addSeparator()
        functions = menu.addMenu(tr("Functions"))
        _, _, formula, _ = _modules()
        for name in getattr(formula, "FUNCTIONS", ()):
            hint = _HINTS.get(name, "value")
            action = functions.addAction(f"{name}({hint})")
            action.triggered.connect(
                lambda _c=False, n=name: self.formula_edit.insert_text(n + "()", 1))
