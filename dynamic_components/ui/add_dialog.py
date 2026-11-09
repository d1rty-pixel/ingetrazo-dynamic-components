"""The small modal that picks the dynamic component a group goes into."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QLabel, QListWidget,
                               QListWidgetItem, QVBoxLayout)

from ..i18n import tr
from .common import Lengths, muted


def _modules():
    from .. import binding
    return binding


def _names(groups) -> str:
    shown = [f"“{g.name or tr('Group')}”" for g in groups[:3]]
    if len(groups) > 3:
        shown.append(tr("{n} more").replace("{n}", str(len(groups) - 3)))
    return ", ".join(shown)


class AddDialog(QDialog):
    def __init__(self, scene, groups, roots, parent=None):
        super().__init__(parent)
        binding = _modules()
        self.setWindowTitle(tr("Add to Dynamic Component"))
        self.setModal(True)
        self.setMinimumWidth(340)
        lay = QVBoxLayout(self)
        intro = QLabel(tr("Add {names} to:").replace("{names}", _names(list(groups))))
        intro.setWordWrap(True)
        lay.addWidget(intro)
        self.list = QListWidget()
        lengths = Lengths()
        rows = []
        for root in roots:
            spec = binding.definition(scene, root)
            if spec is None or binding.add_problem(scene, groups, root):
                continue
            name = root.name or spec.get("name") or tr("Dynamic component")
            rows.append((root, name, len(spec["nodes"]) - 1))
        names = [name for _r, name, _n in rows]
        for root, name, parts in rows:
            count = (tr("1 part") if parts == 1
                     else tr("{n} parts").replace("{n}", str(parts)))
            text = f"{name}  ·  {count}"
            if names.count(name) > 1 and root.xform is not None:
                # Same-named instances are told apart by where they stand.
                o = root.xform.column(3).toVector3D()
                text += "  ·  " + tr("at {p}").replace(
                    "{p}", ", ".join(lengths.number_text(v) for v in (o.x(), o.y(), o.z()))
                    + lengths.suffix)
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, root)
            item.setToolTip(text)
            self.list.addItem(item)
        row_height = max(18, self.list.sizeHintForRow(0)) if rows else 18
        self.list.setFixedHeight(row_height * min(max(len(rows), 3), 8) + 6)
        lay.addWidget(self.list)
        self.note = muted(QLabel(tr(
            "The group keeps its place in the model and becomes a part: it gets "
            "its own section in the Dynamic Components tab.")), small=True)
        self.note.setWordWrap(True)
        lay.addWidget(self.note)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText(tr("Add"))
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        lay.addWidget(self.buttons)
        self.list.itemDoubleClicked.connect(lambda _i: self.accept())
        self.list.currentRowChanged.connect(self._sync)
        if self.list.count():
            self.list.setCurrentRow(0)
        self._sync()

    def _sync(self, *_a) -> None:
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(
            self.list.currentItem() is not None)

    def chosen(self):
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item is not None else None
