"""The Dynamic Components tab: options and attributes of the selection in one place."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from ..i18n import tr
from .attributes import AttributesEditor
from .common import KEY, error_label, host_fold, muted
from .options import OptionsForm


def _modules():
    from .. import binding, evaluate
    return binding, evaluate


def _component(group) -> bool:
    is_component = getattr(group, "is_component", None)
    return bool(is_component and is_component())


class DynamicPanel(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.group = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 9, 6, 9)

        head = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.title = QLabel(tr("Dynamic Components"))
        self.title.setTextFormat(Qt.PlainText)
        self.title.setWordWrap(True)
        self.title.setStyleSheet("font-size: 16px; font-weight: bold")
        self.subtitle = muted(QLabel())
        titles.addWidget(self.title)
        titles.addWidget(self.subtitle)
        head.addLayout(titles, 1)
        self.bake_button = QPushButton(tr("Bake"))
        self.bake_button.setToolTip(tr(
            "Freeze the component as it is now: it keeps its geometry and "
            "becomes a plain component without attributes or formulas."))
        head.addWidget(self.bake_button, 0, Qt.AlignTop)
        outer.addLayout(head)

        self.placeholder = muted(QLabel(tr(
            "Select a dynamic component to see its options and attributes.")))
        self.placeholder.setWordWrap(True)
        outer.addWidget(self.placeholder)
        self.make_button = QPushButton(tr("Make Dynamic"))
        self.make_button.setToolTip(tr(
            "Turn the selected component into a dynamic one; its parts get "
            "attributes you can drive with formulas."))
        outer.addWidget(self.make_button, 0, Qt.AlignLeft)
        self.status = error_label()
        outer.addWidget(self.status)

        # Groups moved into the component (the host does not let one be made
        # inside a component) are kept, but are no part until registered.
        self.loose_box = QFrame()
        self.loose_box.setObjectName("loose")
        self.loose_box.setStyleSheet(
            "QFrame#loose { border: 1px solid #e79b38; border-radius: 4px; }")
        loose = QHBoxLayout(self.loose_box)
        loose.setContentsMargins(8, 6, 8, 6)
        self.loose_label = QLabel()
        self.loose_label.setWordWrap(True)
        self.loose_button = QPushButton(tr("Add as part"))
        loose.addWidget(self.loose_label, 1)
        loose.addWidget(self.loose_button, 0, Qt.AlignVCenter)
        self.loose_box.setVisible(False)
        outer.addWidget(self.loose_box)

        # Parts of the definition deleted from this instance.
        self.missing_box = QFrame()
        self.missing_box.setObjectName("missing")
        self.missing_box.setStyleSheet(
            "QFrame#missing { border: 1px solid palette(mid); border-radius: 4px; }")
        missing = QHBoxLayout(self.missing_box)
        missing.setContentsMargins(8, 6, 8, 6)
        self.missing_label = muted(QLabel())
        self.missing_label.setWordWrap(True)
        self.missing_button = QPushButton(tr("Remove from definition"))
        self.missing_button.setToolTip(tr(
            "Formulas that still read it will show an error. Other copies of "
            "this component keep their group, as a plain group."))
        missing.addWidget(self.missing_label, 1)
        missing.addWidget(self.missing_button, 0, Qt.AlignVCenter)
        self.missing_box.setVisible(False)
        outer.addWidget(self.missing_box)

        # The host has the component open for editing: shown, not editable.
        self.open_note = QLabel()
        self.open_note.setWordWrap(True)
        self.open_note.setStyleSheet("color: #e79b38;")
        self.open_note.setVisible(False)
        outer.addWidget(self.open_note)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        outer.addWidget(self.scroll, 1)
        content = QWidget()
        self.scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self.options_fold = host_fold(tr("Options"), "dynamic_components/open_options")
        body = QVBoxLayout(self.options_fold.body)
        body.setContentsMargins(6, 6, 6, 6)
        self.options = OptionsForm(app)
        body.addWidget(self.options)
        layout.addWidget(self.options_fold)

        self.attributes = AttributesEditor(app)
        layout.addWidget(self.attributes)
        layout.addStretch(1)

        self.bake_button.clicked.connect(self.bake)
        self.make_button.clicked.connect(self.make_dynamic)
        self.loose_button.clicked.connect(self.add_parts)
        self.missing_button.clicked.connect(self.remove_missing)
        self.refresh()

    # ---------------------------------------------------------------- state

    def _selected(self):
        picked = list(self.app.scene.selection)
        if len(picked) != 1 or not hasattr(picked[0], "ext"):
            return None
        return picked[0]

    def _target(self):
        """The selected dynamic component; else the one the host has open for
        editing (selecting inside it picks its parts, not it)."""
        binding, _ = _modules()
        group = self._selected()
        if group is not None and binding.is_dynamic(group):
            return group, False
        scene = self.app.scene
        if getattr(scene, "edit_group", None) is not None:
            open_roots = [r for r in binding.dynamic_roots(scene)
                          if binding.is_open(scene, r)]
            if open_roots:
                return open_roots[-1], True
        return group, False

    def refresh(self) -> None:
        binding, evaluate = _modules()
        group, opened = self._target()
        dynamic = group is not None and binding.is_dynamic(group)
        definition = binding.definition(self.app.scene, group) if dynamic else None
        if definition is None:
            self.group = None
            self.title.setText(tr("Dynamic Components"))
            self.subtitle.setText("")
            self.subtitle.setVisible(False)
            self.bake_button.setVisible(False)
            self.scroll.setVisible(False)
            self.placeholder.setVisible(True)
            self.make_button.setVisible(
                group is not None and not dynamic and _component(group))
            self.loose_box.setVisible(False)
            self.missing_box.setVisible(False)
            self.open_note.setVisible(False)
            self.attributes.clear()
            return
        self.group = group
        inst = group.ext.get(KEY, {})
        present = binding.present_parts(group)
        parts = len(present)
        self.title.setText(str(definition.get("name") or tr("Dynamic component")))
        self.subtitle.setText(tr("Dynamic component · {n} parts").replace("{n}", str(parts))
                              if parts != 1 else tr("Dynamic component · 1 part"))
        self.subtitle.setVisible(True)
        self.bake_button.setVisible(True)
        self.placeholder.setVisible(False)
        self.make_button.setVisible(False)
        self.scroll.setVisible(True)
        try:
            result = evaluate.evaluate(definition, inst.get("set") or {}, inst.get("last"))
        except Exception:  # noqa: BLE001 - the form still shows stored values
            result = None
        self.options.show_group(group, definition, result)
        self.attributes.show_group(group, definition, inst, present=present)
        self._show_loose(binding.loose_children(group))
        self._show_missing(definition, binding.missing_parts(self.app.scene, group))
        self._show_open(opened)

    def _show_open(self, opened) -> None:
        self.open_note.setVisible(opened)
        if opened:
            self.open_note.setText(tr(
                "You are editing inside this component. Leave it (Esc, or click "
                "outside it) to change its options and attributes."))
        for widget in (self.scroll.widget(), self.bake_button, self.loose_button,
                       self.missing_button):
            widget.setEnabled(not opened)
        if not opened:
            self.loose_button.setEnabled(not self.attributes.dirty)
            self.missing_button.setEnabled(not self.attributes.dirty)

    def _show_missing(self, definition, missing) -> None:
        from .common import node_title
        self.missing_box.setVisible(bool(missing))
        self._missing = list(missing)
        if not missing:
            return
        names = ", ".join(f"“{node_title(definition, n)}”" for n in missing[:5])
        if len(missing) > 5:
            names += ", …"
        self.missing_label.setText(
            (tr("{names} is in the definition but has no group here (deleted).")
             if len(missing) == 1 else
             tr("{names} are in the definition but have no group here (deleted)."))
            .replace("{names}", names))

    def _show_loose(self, loose) -> None:
        self.loose_box.setVisible(bool(loose))
        if not loose:
            return
        names = ", ".join(f"“{g.name or tr('Group')}”" for g in loose[:5])
        if len(loose) > 5:
            names += ", …"
        self.loose_label.setText(
            (tr("{names} is in the component but not a part yet: no attributes, "
                "and the formulas do not move it.") if len(loose) == 1 else
             tr("{names} are in the component but no parts yet: no attributes, "
                "and the formulas do not move them.")).replace("{names}", names))
        self.loose_button.setText(tr("Add as part") if len(loose) == 1
                                  else tr("Add as parts"))
        blocked = self.attributes.dirty
        self.loose_button.setEnabled(not blocked)
        self.loose_button.setToolTip(
            tr("Apply or discard your attribute changes first.") if blocked else
            tr("Register it in the definition with its current place and size; "
               "then it gets its own section below."))

    def reveal_parts(self, names) -> None:
        """After parts were added: show them unfolded and in view."""
        self.refresh()
        editor = self.attributes
        for name in names:
            editor._open[(editor.def_id, name)] = True
        editor._shape = None
        self.refresh()
        fold = editor._folds.get(names[-1]) if names else None
        if fold is not None:
            self.scroll.ensureWidgetVisible(fold)

    def show_options(self) -> None:
        self.refresh()
        set_open = getattr(self.options_fold, "set_open", None)
        if set_open is not None:
            set_open(True)
        self.scroll.verticalScrollBar().setValue(0)

    # -------------------------------------------------------------- actions

    def _run(self, label, mutate, group) -> None:
        binding, _ = _modules()
        try:
            binding.run(self.app.viewport, mutate, [group], label)
        except Exception as exc:  # noqa: BLE001 - a Qt slot must not raise
            self.status.setText(f"{label}: {exc}")
            self.status.setVisible(True)
            return
        self.status.setVisible(False)
        self.refresh()

    def bake(self) -> None:
        group = self.group
        if group is None:
            return
        binding, _ = _modules()
        self._run(tr("Bake dynamic component"), lambda s: binding.bake(s, group), group)

    def add_parts(self) -> None:
        group = self.group
        if group is None or self.attributes.dirty:
            return
        binding, _ = _modules()
        self._run(tr("Add parts to dynamic component"),
                  lambda s: binding.add_parts(s, group), group)

    def remove_missing(self) -> None:
        group = self.group
        names = list(getattr(self, "_missing", []))
        if group is None or not names or self.attributes.dirty:
            return
        binding, _ = _modules()
        self._run(tr("Remove parts from dynamic component"),
                  lambda s: binding.remove_parts(s, group, names), group)

    def make_dynamic(self) -> None:
        group = self._selected()
        if group is None:
            return
        binding, _ = _modules()
        self._run(tr("Make dynamic"), lambda s: binding.make_dynamic(s, group), group)
