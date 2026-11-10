"""Shared pieces of the side-tray UI: units, human labels, value editors."""
from __future__ import annotations

import math

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFrame,
                               QLabel, QLineEdit, QSizePolicy, QSpinBox,
                               QToolButton, QVBoxLayout, QWidget)

from ..i18n import N_, tr

KEY = "dynamic_components"
BIG = 1.0e6

# Reserved attributes in the order a user thinks of them, with readable labels.
RESERVED_LABELS = {
    "lenx": N_("Size X"), "leny": N_("Size Y"), "lenz": N_("Size Z"),
    "x": N_("Position X"), "y": N_("Position Y"), "z": N_("Position Z"),
    "rotx": N_("Rotation X"), "roty": N_("Rotation Y"), "rotz": N_("Rotation Z"),
    "hidden": N_("Hidden"), "material": N_("Material"), "copies": N_("Copies"),
}
ROOT_RESERVED = ("lenx", "leny", "lenz")
TYPE_LABELS = {
    "length": N_("Length"), "float": N_("Number"), "int": N_("Whole number"),
    "bool": N_("Yes / No"), "string": N_("Text"), "choice": N_("Choice"),
    "material": N_("Material"),
}
ACCESS_LABELS = {
    "none": N_("Hidden from users"),
    "view": N_("Shown, read-only"),
    "textbox": N_("Users can edit"),
    "list": N_("Users pick from a list"),
    "warn": N_("Shown as a warning"),
}
GENERATOR_LABELS = {"board@1": N_("Board with holes, pockets and grooves")}
_ANGLES = frozenset({"rotx", "roty", "rotz"})
# Spin-box decimals per document unit: about 0.1-1 mm per step (as Newton).
_DECIMALS = {"m": 3, "cm": 2, "mm": 1, "in": 2, "in-frac": 2, "ft": 3,
             "ft-in": 3, "ft-in-frac": 3}


class Lengths:
    """The document's length unit: numbers shown = metres * factor."""

    def __init__(self):
        self.factor, self.suffix, self.decimals = 1.0, " m", 3
        self._fmt = None
        try:
            from core import units
            name = units.model_unit()
            self.factor = units.length_number(1.0, name)
            self.suffix = units.length_suffix(name)
            self.decimals = _DECIMALS.get(name, 3)
            # At least to the millimetre: at the document's default precision
            # (2 decimals in m) a 16 mm board would read «0.02 m».
            self._fmt = getattr(units, "fmt_len_fine", units.fmt_len)
        except Exception:  # noqa: BLE001 - outside the host: plain metres
            pass

    def show(self, metres: float) -> float:
        return float(metres) * self.factor

    def si(self, number: float) -> float:
        return float(number) / self.factor

    def text(self, metres: float) -> str:
        if self._fmt is not None:
            try:
                return self._fmt(float(metres))
            except Exception:  # noqa: BLE001
                pass
        return f"{self.show(metres):.{self.decimals}f}{self.suffix}"

    def number_text(self, metres: float) -> str:
        """The bare number in the document unit, trailing zeros dropped."""
        text = f"{self.show(metres):.{self.decimals}f}"
        return text.rstrip("0").rstrip(".") if "." in text else text

    def parse(self, text: str) -> float:
        """A number typed in the document unit (a trailing unit is ignored)."""
        cleaned = text.strip().replace(",", ".")
        for suffix in (self.suffix.strip(), "mm", "cm", "m", '"', "'"):
            if suffix and cleaned.endswith(suffix):
                cleaned = cleaned[: -len(suffix)].strip()
                break
        return self.si(float(cleaned))


def is_reserved(name: str) -> bool:
    return name in RESERVED_LABELS


def attr_label(name: str, attr: dict) -> str:
    """What a user calls the attribute: its label, else a readable default."""
    label = (attr or {}).get("label") or ""
    if label and label.lower() != name:
        return label
    if name in RESERVED_LABELS:
        return tr(RESERVED_LABELS[name])
    return label or name


def node_title(spec: dict, node: str) -> str:
    if node == "":
        return str(spec.get("name") or tr("Component"))
    label = spec["nodes"][node].get("label") or node
    if label == node:  # only the stored key: make it readable
        label = node.replace("_", " ").strip().capitalize() or node
    return label


def reference(from_node: str, to_node: str, name: str) -> str:
    """How a formula on ``from_node`` names ``to_node``'s attribute."""
    if to_node == from_node:
        return name
    if to_node == "":
        return f"Parent!{name}"
    return f"{to_node}!{name}"


def _close(a, b) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-9)
    return a == b


def same_value(a, b) -> bool:
    return _close(a, b)


def value_text(kind: str, value, lengths: Lengths, name: str = "") -> str:
    if value is None:
        return "—"
    if isinstance(value, bool) or kind == "bool":
        return tr("Yes") if bool(value) else tr("No")
    if kind == "length" and isinstance(value, (int, float)):
        return lengths.text(value)
    if kind == "int" and isinstance(value, (int, float)):
        return str(int(value))
    if isinstance(value, float):
        text = f"{round(value, 4):g}"
        return text + ("°" if name in _ANGLES else "")
    return str(value)


def option_text(label, value, kind, lengths) -> str:
    return str(label) if label not in (None, "") else value_text(kind, value, lengths)


class _NoWheel(QObject):
    """A wheel over an unfocused field scrolls the tray, never the value: in a
    scroll area a stray wheel would otherwise change the model (an undo step)."""

    def eventFilter(self, obj, event):  # noqa: N802 - Qt override
        if event.type() == QEvent.Wheel and not obj.hasFocus():
            event.ignore()
            return True
        return False


_NO_WHEEL = None


def scroll_safe(widget):
    global _NO_WHEEL
    if _NO_WHEEL is None:
        _NO_WHEEL = _NoWheel()
    widget.setFocusPolicy(Qt.StrongFocus)
    widget.installEventFilter(_NO_WHEEL)
    return widget


def narrow(widget):
    """Let a field shrink with a narrow side tray instead of widening it."""
    if isinstance(widget, QComboBox):
        widget.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        widget.setMinimumContentsLength(6)
    widget.setSizePolicy(QSizePolicy.Ignored, widget.sizePolicy().verticalPolicy())
    widget.setMinimumWidth(48)
    return widget


class ValueEditor:
    """One typed field for a value. ``read()`` returns the stored form (metres
    for lengths); ``changed`` is the signal that fires when the user is done;
    ``set(value)`` updates it without firing."""

    def __init__(self, kind: str, value, lengths: Lengths, *, name: str = "",
                 options=None, minimum=None, maximum=None, as_list=False):
        self.kind = kind
        self.lengths = lengths
        if (as_list or kind == "choice") and options:
            self._combo(options, value)
        elif kind == "length":
            spin = QDoubleSpinBox()
            spin.setDecimals(lengths.decimals)
            spin.setRange(lengths.show(minimum) if minimum is not None else -BIG,
                          lengths.show(maximum) if maximum is not None else BIG)
            spin.setSuffix(lengths.suffix)
            spin.setKeyboardTracking(False)
            self.widget, self.changed = spin, spin.valueChanged
            self._read = lambda: lengths.si(spin.value())
            self._write = lambda v: spin.setValue(lengths.show(float(v or 0.0)))
        elif kind == "float":
            spin = QDoubleSpinBox()
            spin.setDecimals(4)
            spin.setRange(minimum if minimum is not None else -BIG,
                          maximum if maximum is not None else BIG)
            if name in _ANGLES:
                spin.setSuffix(" °")
            spin.setKeyboardTracking(False)
            self.widget, self.changed = spin, spin.valueChanged
            self._read = spin.value
            self._write = lambda v: spin.setValue(float(v or 0.0))
        elif kind == "int":
            spin = QSpinBox()
            spin.setRange(int(minimum) if minimum is not None else -int(BIG),
                          int(maximum) if maximum is not None else int(BIG))
            spin.setKeyboardTracking(False)
            self.widget, self.changed = spin, spin.valueChanged
            self._read = spin.value
            self._write = lambda v: spin.setValue(int(v or 0))
        elif kind == "bool":
            check = QCheckBox()
            self.widget, self.changed = check, check.toggled
            self._read = check.isChecked
            self._write = lambda v: check.setChecked(bool(v))
        else:
            edit = QLineEdit()
            self.widget, self.changed = edit, edit.editingFinished
            self._read = edit.text
            self._write = lambda v: edit.setText("" if v is None else str(v))
        if not isinstance(self.widget, QCheckBox):
            narrow(self.widget)
        scroll_safe(self.widget)
        self.set(value)

    def _combo(self, options, value):
        combo = QComboBox()
        for label, data in options:
            combo.addItem(option_text(label, data, self.kind, self.lengths), data)
        self.widget, self.changed = combo, combo.activated

        def write(v):
            index = next((i for i in range(combo.count())
                          if same_value(combo.itemData(i), v)), -1)
            if index < 0 and v is not None:
                combo.addItem(value_text(self.kind, v, self.lengths), v)
                index = combo.count() - 1
            combo.setCurrentIndex(max(index, 0))
        self._read = combo.currentData
        self._write = write

    def read(self):
        return self._read()

    def set(self, value) -> None:
        self.widget.blockSignals(True)
        try:
            self._write(value)
        finally:
            self.widget.blockSignals(False)


class Fold(QWidget):
    """A section that folds away with a click on its title — the look of the
    host's FoldSection (Newton, Render and AI tabs). The open state is kept by
    the owner, not in the settings: part sections come and go with the model."""

    def __init__(self, title: str, open_: bool = True, on_toggle=None, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        self.header = QToolButton()
        self.header.setText(title.replace("&", "&&"))
        self.header.setCheckable(True)
        self.header.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.header.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.header.setStyleSheet("QToolButton { border: none; font-weight: bold; "
                                  "text-align: left; padding: 3px 0; }")
        lay.addWidget(self.header)
        self.body = QFrame()
        self.body.setFrameShape(QFrame.StyledPanel)
        lay.addWidget(self.body, 1)
        self._on_toggle = on_toggle
        self.header.setChecked(open_)
        self._show(open_)
        self.header.toggled.connect(self._toggled)

    def is_open(self) -> bool:
        return self.header.isChecked()

    def set_open(self, on: bool) -> None:
        self.header.setChecked(on)

    def set_title(self, title: str) -> None:
        self.header.setText(title.replace("&", "&&"))

    def _toggled(self, on: bool) -> None:
        self._show(on)
        if self._on_toggle is not None:
            self._on_toggle(on)

    def _show(self, on: bool) -> None:
        self.header.setArrowType(Qt.DownArrow if on else Qt.RightArrow)
        self.body.setVisible(on)


def host_fold(title: str, settings_key: str, default_open: bool = True):
    """The host's own FoldSection (its open state survives restarts); the local
    look-alike when the host does not have it."""
    try:
        from views.fold_section import FoldSection
        return FoldSection(title.replace("&", "&&"), settings_key,
                           default_open=default_open)
    except Exception:  # noqa: BLE001
        return Fold(title, default_open)


def muted(label: QLabel, *, small=False, mono=False) -> QLabel:
    parts = ["color: palette(placeholder-text);"]
    if small:
        parts.append("font-size: 11px;")
    if mono:
        parts.append("font-family: monospace;")
    label.setStyleSheet(" ".join(parts))
    return label


def warning_label(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setTextFormat(Qt.PlainText)
    label.setObjectName("warning")
    label.setStyleSheet("color: #b9770e;")
    return label


def error_label(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setObjectName("error")
    label.setStyleSheet("color: #c0392b;")
    label.setVisible(bool(text))
    return label
