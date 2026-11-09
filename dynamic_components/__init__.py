"""Dynamic components for IngeTrazo: attributes and formulas that drive a
component's parts."""

__version__ = "0.1.0"

import logging

from PySide6.QtCore import Qt

from .i18n import tr

KEY = "dynamic_components"
_log = logging.getLogger(__name__)
_SCALE_EPS = 1e-6


def _single_instance(selection):
    picked = list(selection)
    if len(picked) != 1:
        return None
    group = picked[0]
    is_component = getattr(group, "is_component", None)
    if is_component is None or not is_component():
        return None
    return group


def _has_scale(xform):
    if xform is None:
        return False
    for i in range(3):
        col = xform.column(i)
        length = (col.x() ** 2 + col.y() ** 2 + col.z() ** 2) ** 0.5
        if abs(length - 1.0) > _SCALE_EPS:
            return True
    return False


def _scale_key(xform):
    return tuple(round(v, 6) for v in xform.data())


def _outliner_kind(binding, app):
    def kind(group):
        if not binding.is_dynamic(group):
            return None
        props = []
        spec = binding.definition(app.scene, group)
        if spec is None:
            return None
        inst = group.ext.get(KEY, {})
        values = inst.get("last") or {}
        from . import spec as spec_mod
        for node, name, attr in spec_mod.editable_attrs(spec)[:4]:
            value = values.get(node, {}).get(name, attr.get("value"))
            props.append((attr.get("label") or name, str(value)))
        return {"type": tr("Dynamic component"), "props": props}
    return kind


def setup(app):
    from . import binding
    from .ui.attributes import AttributesPanel
    from .ui.options import OptionsDialog

    if app.api_version != 2:
        raise RuntimeError("Requires IngeTrazo 0.6.0 / Extension API 2")

    panel = AttributesPanel(app)
    app.add_panel(tr("Dynamic Components"), panel, start_hidden=True)

    def run(label, fn, group):
        try:
            binding.run(app.viewport, fn, [group], label)
        except Exception as exc:  # noqa: BLE001 - a Qt slot must not raise
            _log.warning("%s failed: %s", label, exc)
            flash = getattr(app.viewport, "flash_status", None)
            if callable(flash):
                flash(f"{label}: {exc}", 5000)

    def open_options(group):
        from PySide6.QtCore import QTimer

        def show():
            dialog = OptionsDialog(app, group, app.window)
            dialog.setAttribute(Qt.WA_DeleteOnClose)
            dialog.show()
        QTimer.singleShot(0, show)

    def context_menu(menu, selection):
        group = _single_instance(selection)
        if group is None:
            return
        if not binding.is_dynamic(group):
            menu.addAction(
                tr("Make Dynamic"),
                lambda: run(tr("Make dynamic"),
                            lambda s: binding.make_dynamic(s, group), group))
            return
        menu.addAction(tr("Component Options…"),
                       lambda: open_options(group))
        menu.addAction(
            tr("Bake Dynamic Component"),
            lambda: run(tr("Bake dynamic component"),
                        lambda s: binding.bake(s, group), group))

    app.add_context_menu(context_menu)
    app.add_outliner_kind(_outliner_kind(binding, app))

    busy = []
    tried = {}

    def candidates():
        scene = app.scene
        seen = set()
        for group in list(scene.groups) + list(scene.selection):
            if id(group) not in seen and hasattr(group, "ext"):
                seen.add(id(group))
                yield group

    def on_document_changed():
        if busy:
            return
        busy.append(True)
        try:
            panel.refresh()
            for group in candidates():
                if not binding.is_dynamic(group) or not _has_scale(group.xform):
                    continue
                if not binding.absorbable_axes(app.scene, group):
                    continue
                key = _scale_key(group.xform)
                if tried.get(id(group)) == key:
                    continue
                tried[id(group)] = key
                run(tr("Dynamic component scale"),
                    lambda s, g=group: binding.absorb_scale(s, g), group)
        finally:
            busy.pop()

    app.on_document_changed(on_document_changed)
