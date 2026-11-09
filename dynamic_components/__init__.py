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
    # Undo-stack commands already looked at. The Scale tool's live preview
    # writes the scale into the xform on every mouse move (from the grip's
    # original, never as a step from the last frame) and the viewport reports
    # each frame as a document change. Absorbing there turned every frame into
    # an undo step and multiplied LenX/Y/Z frame after frame. Only a scale
    # that arrived with a NEW command (the tool's commit, a typed value, an
    # undo/redo lands on a command we have seen) is absorbed.
    handled = []

    def _top_command():
        stack = getattr(getattr(app.viewport, "history", None), "undo_stack", None)
        return stack[-1] if stack else None

    def _mark_handled(cmd):
        if cmd is not None and not any(cmd is c for c in handled):
            handled.append(cmd)
            del handled[:-64]

    def committed_since_last_look():
        top = _top_command()
        if top is None or any(top is c for c in handled):
            return False
        _mark_handled(top)
        return True

    def candidates():
        scene = app.scene
        seen = set()
        for group in list(scene.groups) + list(scene.selection):
            if id(group) not in seen and hasattr(group, "ext"):
                seen.add(id(group))
                yield group

    # Instances laid out for a scale that is only previewed: their parts must
    # go back to the stored layout when that scale goes away (Esc, undo).
    previewed = {}

    def redraw():
        app.scene.version += 1
        update = getattr(app.viewport, "update", None)
        if callable(update):
            update()

    def quietly(fn, group):
        """A placement-only write outside the undo stack; never raises."""
        try:
            return fn(app.scene, group)
        except Exception as exc:  # noqa: BLE001 - a redraw hook must not raise
            _log.warning("Dynamic component preview failed: %s", exc)
            return False

    def on_document_changed():
        if busy:
            return
        busy.append(True)
        try:
            panel.refresh()
            committed = committed_since_last_look()
            moved = False
            seen = set()
            for group in candidates():
                if not binding.is_dynamic(group):
                    continue
                seen.add(id(group))
                if binding.is_open(app.scene, group):
                    # The host edits inside it in world coordinates (it
                    # pushed the matrix down); settled once it is left.
                    continue
                scaled = (_has_scale(group.xform)
                          and binding.absorbable_axes(app.scene, group))
                if scaled and committed:
                    key = _scale_key(group.xform)
                    if tried.get(id(group)) == key:
                        continue
                    tried[id(group)] = key
                    previewed.pop(id(group), None)
                    run(tr("Dynamic component scale"),
                        lambda s, g=group: binding.absorb_scale(s, g), group)
                    # Our own step: the next look must not count it as new work.
                    _mark_handled(_top_command())
                elif scaled:
                    # A tool's live preview: keep boards their thickness while
                    # dragging; nothing is stored, no undo step.
                    previewed[id(group)] = group
                    moved |= bool(quietly(binding.preview_scale, group))
                elif id(group) in previewed:
                    del previewed[id(group)]
                    moved |= bool(quietly(binding.relayout, group))
                else:
                    # After an edit inside it the host leaves the matrix in
                    # the parts: pull it back up. Then the parts follow the
                    # definition again (a deleted part's undo, a stray move).
                    moved |= bool(quietly(binding.settle, group))
                    moved |= bool(quietly(binding.relayout, group))
            for key in [k for k in previewed if k not in seen]:
                del previewed[key]
            if moved:
                redraw()
        finally:
            busy.pop()

    app.on_document_changed(on_document_changed)
