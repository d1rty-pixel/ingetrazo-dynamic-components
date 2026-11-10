"""The System 32 cabinet end to end: template, generators, cutters, undo,
hand edits, scale preview, bake, .igz, and its options in the panel."""
from types import SimpleNamespace

import pytest
from PySide6.QtGui import QMatrix4x4

from core.history import History
from core.mesh import Mesh
from core.scene import Scene
from core.solids import solid_report

from dynamic_components import binding
from cabinet_builder import build as templates
from dynamic_components import evaluate as ev

KEY = binding.KEY


@pytest.fixture
def cabinet(qtapp):
    scene = Scene()
    root = templates.insert_cabinet(scene)
    return scene, root


def parts(root, name):
    return [c for c in root.children
            if ((c.ext or {}).get(KEY) or {}).get("part") == name]


def values(root):
    return root.ext[KEY]["last"][""]


def test_template_lays_out_plinth_shelves_and_holes(cabinet):
    scene, root = cabinet
    v = values(root)
    assert v["z_bottom"] == pytest.approx(0.1)
    assert v["n"] == 4 and v["holes_k"] == 57 and v["warning"] == ""
    assert v["row_back"] == pytest.approx(0.037 + 14 * 0.032)
    assert binding.problems(root) == {}
    assert len(parts(root, "shelf")) == 4
    assert all(len(parts(root, r)) == 57 for r in ("holes_lf", "holes_lb", "holes_rf", "holes_rb"))


def test_sides_are_real_drilled_solids_without_scale(cabinet):
    _, root = cabinet
    for name in ("side_left", "side_right"):
        side = parts(root, name)[0]
        ok, vol = solid_report(side.mesh)
        assert ok
        assert len(side.mesh.faces) == 6 + 4 + 114 * 13       # 2 rows × 57 blind holes
        assert vol < 0.019 * 0.56 * 2.0
        assert [round(side.xform.column(i).toVector3D().length(), 9) for i in range(3)] == [1, 1, 1]
    left, right = parts(root, "side_left")[0], parts(root, "side_right")[0]
    assert left.mesh is not right.mesh                      # holes on opposite faces


def test_cutters_are_never_drawn(cabinet):
    _, root = cabinet
    for name in ("holes_lf", "holes_rb"):
        assert all(c.hidden for c in parts(root, name))


def test_shelves_sit_on_the_raster_and_keep_the_gap_limits(cabinet):
    _, root = cabinet
    v = values(root)
    z_first, support = v["z_first"], v["support"]
    zs = sorted(c.xform.column(3).z() for c in parts(root, "shelf"))
    for z in zs:
        k = (z - support - z_first) / 0.032
        assert k == pytest.approx(round(k), abs=1e-4)
    tops = [v["in_low"]] + [z + 0.019 for z in zs]
    bottoms = zs + [v["in_top"]]
    for low, high in zip(tops, bottoms):
        assert v["gap_min"] <= high - low <= v["gap_max"]


def test_options_change_the_layout(cabinet):
    scene, root = cabinet
    binding.set_values(scene, root, {"": {"plinth": False, "lenz": 1.2}})
    v = values(root)
    assert v["z_bottom"] == 0 and v["n"] == 3 and v["holes_k"] == 35
    assert parts(root, "plinth")[0].hidden
    side = parts(root, "side_left")[0]
    assert side.ext[KEY]["gen"]["lens"][2] == pytest.approx(1.2)
    assert len(side.mesh.faces) == 6 + 4 + 70 * 13
    binding.set_values(scene, root, {"": {"drill": False}})
    assert len(parts(root, "side_left")[0].mesh.faces) == 6 + 4     # the groove stays


def test_fixed_mode_and_warning(cabinet):
    scene, root = cabinet
    binding.set_values(scene, root, {"": {"gap_min": 0.5, "gap_max": 0.52}})
    assert "cannot both be kept" in values(root)["warning"]
    binding.set_values(scene, root, {"": {"shelf_mode": "fixed", "shelves": 1,
                                          "gap_min": 0.18, "gap_max": 0.38}})
    v = values(root)
    assert v["n"] == 1 and "outside" in v["warning"]
    assert len(parts(root, "shelf")) == 1


def test_show_if_follows_the_options(cabinet):
    scene, root = cabinet
    spec = binding.definition(scene, root)
    inst = root.ext[KEY]
    r = ev.evaluate(spec, inst["set"], inst["last"])
    assert r.visible[("", "shelves")] is False and r.visible[("", "n")] is True
    assert r.visible[("", "plinth_h")] is True
    binding.set_values(scene, root, {"": {"plinth": False, "shelf_mode": "fixed"}})
    r = ev.evaluate(spec, inst["set"], inst["last"])
    assert r.visible[("", "shelves")] is True and r.visible[("", "plinth_h")] is False


def test_undo_restores_meshes(cabinet):
    scene, root = cabinet
    hist = History(scene)
    side = parts(root, "side_left")[0]
    before = side.mesh
    hist.execute(binding.DynamicCommand(
        lambda s: binding.set_values(s, root, {"": {"lenz": 1.5}}), [root]))
    after = side.mesh
    assert after is not before
    hist.undo()
    assert side.mesh is before and len(parts(root, "shelf")) == 4
    hist.redo()
    assert side.mesh is after


def test_equal_inputs_share_one_mesh(qtapp):
    scene = Scene()
    a = templates.insert_cabinet(scene)
    b = templates.insert_cabinet(scene, at=(2.0, 0.0, 0.0))
    assert parts(a, "side_left")[0].mesh is parts(b, "side_left")[0].mesh
    binding.set_values(scene, b, {"": {"lenz": 1.8}})
    assert parts(a, "side_left")[0].mesh is not parts(b, "side_left")[0].mesh


def test_a_hand_edited_part_is_kept_until_regenerated(cabinet):
    scene, root = cabinet
    side = parts(root, "side_left")[0]
    edited = Mesh()
    for face in list(side.mesh.faces)[:6]:
        edited.add_face([v.position for v in face.loop])
    side.mesh = edited
    assert binding.edited_parts(root) == ["side_left"]
    binding.set_values(scene, root, {"": {"lenz": 1.7}})
    assert side.mesh is edited
    assert "Edited by hand" in binding.problems(root)["side_left"][0]
    assert binding.regenerate(scene, root) >= 1
    assert side.mesh is not edited and binding.edited_parts(root) == []
    assert "side_left" not in binding.problems(root)


def test_preview_stretches_generated_parts_without_rebuilding(cabinet):
    scene, root = cabinet
    side = parts(root, "side_left")[0]
    mesh = side.mesh
    scaled = QMatrix4x4()
    scaled.scale(1.0, 1.0, 1.25)
    root.xform = scaled
    shelf = parts(root, "shelf")[0]
    assert binding.preview_scale(scene, root)
    assert side.mesh is mesh
    # The root carries the 1.25 in z: the old 2.0 m side mesh is stretched to
    # 2.5 m in the world, while a shelf keeps its thickness.
    assert (root.xform * side.xform).column(2).toVector3D().length() == pytest.approx(1.25)
    assert (root.xform * shelf.xform).column(2).toVector3D().length() == pytest.approx(1.0)
    root.xform = QMatrix4x4()
    binding.relayout(scene, root)
    assert side.xform.column(2).toVector3D().length() == pytest.approx(1.0)
    root.xform = scaled
    assert binding.absorb_scale(scene, root)
    assert values(root)["lenz"] == pytest.approx(2.5)
    assert side.mesh is not mesh
    assert side.xform.column(2).toVector3D().length() == pytest.approx(1.0)


def test_bake_removes_cutters_and_keeps_holes(cabinet):
    scene, root = cabinet
    side_mesh = parts(root, "side_left")[0].mesh
    binding.bake(scene, root)
    assert not binding.is_dynamic(root)
    # boards + 4 shelves; the unused divider (hidden) is gone with the cutters
    assert len(root.children) == 6 + 4
    assert not any(c.hidden for c in root.children)
    assert any(c.mesh is side_mesh for c in root.children)
    assert all(KEY not in (c.ext or {}) for c in root.children)


def test_igz_round_trip_does_not_rebuild(cabinet, tmp_path):
    from formats import igz
    scene, root = cabinet
    path = tmp_path / "cabinet.igz"
    igz.save_scene(scene, path)
    opened = Scene()
    igz.load_into(opened, path)
    loaded = binding.dynamic_roots(opened)[0]
    side = parts(loaded, "side_left")[0]
    mesh = side.mesh
    assert len(mesh.faces) == 6 + 4 + 114 * 13
    binding.apply(opened, loaded)
    assert side.mesh is mesh                              # key and fingerprint match
    assert binding.problems(loaded) == {}


def test_a_cutter_that_reaches_nothing_is_reported(cabinet):
    scene, root = cabinet
    spec = binding.definition(scene, root)
    spec["nodes"]["holes_lf"]["attrs"]["x"]["formula"] = "=Parent!LenX + 1"
    binding.set_definition(scene, root.ext[KEY]["def"], spec)
    assert "Cuts nothing" in binding.problems(root)["holes_lf"][0]


def test_unknown_generator_keeps_the_last_shape(cabinet):
    scene, root = cabinet
    side = parts(root, "side_left")[0]
    mesh = side.mesh
    spec = binding.definition(scene, root)
    spec["nodes"]["side_left"]["gen"] = "board@9"
    binding.set_definition(scene, root.ext[KEY]["def"], spec)
    assert side.mesh is mesh
    assert "board@9" in binding.problems(root)["side_left"][0]


def test_removing_a_cut_target_frees_its_cutters(cabinet):
    scene, root = cabinet
    binding.remove_parts(scene, root, ["side_left"])
    spec = binding.definition(scene, root)
    assert "cut" not in spec["nodes"]["holes_lf"]
    assert not any(c.hidden for c in parts(root, "holes_lf"))


# ------------------------------------------------------------------ the panel

@pytest.fixture
def app(cabinet):
    scene, root = cabinet
    viewport = SimpleNamespace(scene=scene, history=History(scene),
                               notify_scene_changed=lambda: None)
    scene.selection.clear()
    scene.selection.add(root)
    return SimpleNamespace(scene=scene, viewport=viewport, key=KEY, window=None), root


def _row_shown(row):
    return row.form.isRowVisible(row.field)


def test_options_are_grouped_and_conditional(app):
    from dynamic_components.ui.panel import DynamicPanel
    app_, root = app
    panel = DynamicPanel(app_)
    form = panel.options
    rows = form._rows
    assert set(form._headers) == {"Carcass", "Plinth", "Dividers", "Shelves", "Holes (System 32)"}
    assert not _row_shown(rows[("", "shelves")]) and _row_shown(rows[("", "n")])
    assert not _row_shown(rows[("", "warning")])
    rows[("", "plinth")].editor.set(False)
    form._commit(("", "plinth"))
    assert not _row_shown(rows[("", "plinth_h")])
    form._run({"": {"gap_min": 0.5, "gap_max": 0.52}}, "test")
    assert _row_shown(rows[("", "warning")])
    assert "cannot both" in rows[("", "warning")].warning.text()


def test_attribute_editor_shows_geometry_and_problems(app):
    from dynamic_components.ui.panel import DynamicPanel
    app_, root = app
    panel = DynamicPanel(app_)
    editor = panel.attributes
    assert "⚙" in editor._fold_title("side_left") and "✂" in editor._fold_title("holes_lf")
    editor.set_link("holes_lf", "cut", "")
    spec = binding.definition(app_.scene, root)
    assert "cut" not in spec["nodes"]["holes_lf"]
    assert not parts(root, "holes_lf")[0].hidden
    editor.set_link("holes_lf", "cut", "side_left")
    assert parts(root, "holes_lf")[0].hidden


def test_panel_offers_regenerate_for_hand_edits(app):
    from dynamic_components.ui.panel import DynamicPanel
    app_, root = app
    side = parts(root, "side_left")[0]
    side.mesh = Mesh()
    panel = DynamicPanel(app_)
    assert not panel.edited_box.isHidden()
    panel.regenerate()
    assert panel.edited_box.isHidden()
    assert len(side.mesh.faces) > 6


def test_definition_travels_with_the_instance_into_another_document(cabinet):
    scene, root = cabinet
    assert root.ext[KEY]["spec"] == binding.registry(scene)[root.ext[KEY]["def"]]
    # What a paste into a document without the definition leaves behind.
    other = Scene()
    pasted = binding.copy_group(root)
    other.groups.append(pasted)
    assert binding.registry(other) == {}
    assert binding.definition(other, pasted)["name"] == binding.definition(scene, root)["name"]
    before = len(pasted.children)
    binding.set_values(other, pasted, {"": {"lenz": 1.8}})
    assert values(pasted)["holes_k"] < 57 and len(pasted.children) != before
    assert root.ext[KEY]["def"] in binding.registry(other)       # adopted
    assert values(root)["holes_k"] == 57                          # original untouched


def test_registry_wins_and_a_bad_copy_is_ignored(cabinet):
    scene, root = cabinet
    root.ext[KEY]["spec"] = {"version": 99}
    assert binding.definition(scene, root) is not None            # registry entry
    other = Scene()
    other.groups.append(root)
    assert binding.definition(other, root) is None                # nothing valid
    binding.set_definition(scene, root.ext[KEY]["def"], binding.registry(scene)[root.ext[KEY]["def"]])
    assert root.ext[KEY]["spec"] == binding.registry(scene)[root.ext[KEY]["def"]]



def test_first_and_last_hole_are_the_same_distance_from_the_panels(cabinet):
    scene, root = cabinet
    for height in (2.0, 1.97, 1.2, 0.83):
        binding.set_values(scene, root, {"": {"lenz": height}})
        v = values(root)
        k = v["holes_k"]
        first = v["z_first"]
        last = first + (k - 1) * 0.032
        low, high = first - v["in_low"], v["in_top"] - last
        assert low == pytest.approx(high, abs=1e-6)
        assert low >= v["edge_min"] - 1e-6                 # never closer than the minimum
        assert low < v["edge_min"] + 0.032                 # and no more than one step more
        # the holes really sit there
        zs = sorted(c.xform.column(3).z() + 0.0025 for c in parts(root, "holes_lf"))
        assert len(zs) == k and zs[0] == pytest.approx(first, abs=1e-4)
        assert zs[-1] == pytest.approx(last, abs=1e-4)


def test_no_divider_up_to_the_split_width(cabinet):
    scene, root = cabinet
    assert values(root)["divs"] == 0 and parts(root, "divider")[0].hidden
    binding.set_values(scene, root, {"": {"lenx": 1.0}})
    assert values(root)["divs"] == 0                       # exactly 1000 mm: none yet
    assert all(c.hidden for c in parts(root, "holes_df") + parts(root, "holes_db"))


def test_wide_cabinet_gets_dividers_with_shelves_in_every_field(cabinet):
    scene, root = cabinet
    binding.set_values(scene, root, {"": {"lenx": 1.2}})
    v = values(root)
    assert v["divs"] == 1 and v["fields"] == 2
    assert v["field_w"] == pytest.approx((1.2 - 3 * 0.019) / 2)
    dividers = [c for c in parts(root, "divider") if not c.hidden]
    assert len(dividers) == 1
    x = dividers[0].xform.column(3).x()
    assert x == pytest.approx(0.019 + v["field_w"])        # right after the first field
    # a shelf for every level in every field, all at the same heights
    shelves = parts(root, "shelf")
    assert len(shelves) == v["n"] * 2
    by_x = {}
    for c in shelves:
        by_x.setdefault(round(c.xform.column(3).x(), 4), []).append(c.xform.column(3).z())
    assert len(by_x) == 2
    left, right = (sorted(z) for z in by_x.values())
    assert left == pytest.approx(right)
    # no shelf runs into the divider
    for c in shelves:
        x0 = c.xform.column(3).x()
        assert x0 + v["field_w"] - 0.002 <= x + 1e-9 or x0 >= x + 0.019 - 1e-9


def test_divider_is_drilled_through_in_both_rows(cabinet):
    scene, root = cabinet
    binding.set_values(scene, root, {"": {"lenx": 1.2}})
    divider = [c for c in parts(root, "divider") if not c.hidden][0]
    ok, _vol = solid_report(divider.mesh)
    assert ok
    assert len(divider.mesh.faces) == 6 + 2 * 57 * 12      # 2 rows × 57 through holes
    assert binding.problems(root) == {}


def test_more_width_more_dividers_and_the_split_is_an_option(cabinet):
    scene, root = cabinet
    binding.set_values(scene, root, {"": {"lenx": 2.4}})
    assert values(root)["divs"] == 2                        # 2.4 m: three fields
    assert len([c for c in parts(root, "divider") if not c.hidden]) == 2
    assert len(parts(root, "shelf")) == values(root)["n"] * 3
    binding.set_values(scene, root, {"": {"split": 1.5}})
    assert values(root)["divs"] == 1
    binding.set_values(scene, root, {"": {"split": 3.0}})
    assert values(root)["divs"] == 0


def _size(part):
    """The size of a stretched part: its mesh extent times its scale."""
    pos = [(v.position.x(), v.position.y(), v.position.z()) for v in part.mesh.vertices]
    return tuple(part.xform.column(i).toVector3D().length()
                 * (max(p[i] for p in pos) - min(p[i] for p in pos)) for i in range(3))


def test_back_panel_sits_in_grooves(cabinet):
    scene, root = cabinet
    v = values(root)
    assert v["back_y"] == pytest.approx(0.56 - 0.010 - 0.009)
    assert binding.problems(root) == {}
    # sides, bottom and top are grooved solids; the grooves do not touch the holes
    for name in ("side_left", "side_right", "bottom", "top"):
        board = parts(root, name)[0]
        ok, _ = solid_report(board.mesh)
        assert ok, name
    side = parts(root, "side_left")[0]
    full = 0.019 * 0.56 * 2.0
    _, volume = solid_report(side.mesh)
    assert volume < full - 0.008 * 0.009 * 2.0 + 1e-9      # groove and holes are gone
    # the panel reaches 7 mm into every groove, centred in it, inside the cabinet
    back = parts(root, "back")[0]
    m = back.xform
    x0, y0, z0 = m.column(3).x(), m.column(3).y(), m.column(3).z()
    sx, sy, sz = _size(back)
    assert x0 == pytest.approx(0.019 - 0.007) and y0 == pytest.approx(v["back_y"] + 0.0005)
    assert z0 == pytest.approx(v["in_low"] - 0.007)
    assert x0 + sx == pytest.approx(0.6 - 0.019 + 0.007)
    assert z0 + sz == pytest.approx(v["in_top"] + 0.007)
    # shelves and the hole rows stay in front of it
    shelf = parts(root, "shelf")[0]
    assert shelf.xform.column(3).y() + _size(shelf)[1] < v["back_y"]
    assert v["row_back"] < v["back_y"] - 0.02


def test_without_back_panel_there_are_no_grooves(cabinet):
    scene, root = cabinet
    binding.set_values(scene, root, {"": {"back_panel": False}})
    for name in ("side_left", "bottom"):
        assert len(parts(root, name)[0].mesh.faces) == (6 + 114 * 13 if name == "side_left" else 6)
    assert all(c.hidden for name in ("groove_l", "groove_r", "groove_b", "groove_t")
               for c in parts(root, name))
    assert parts(root, "back")[0].hidden
    binding.set_values(scene, root, {"": {"back_panel": True, "back_inset": 0.02,
                                           "groove_d": 0.01}})
    assert values(root)["back_y"] == pytest.approx(0.56 - 0.02 - 0.009)
    assert binding.problems(root) == {}
