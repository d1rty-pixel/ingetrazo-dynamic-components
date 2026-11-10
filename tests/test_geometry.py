"""geometry.board: pure polygon data, checked without Qt."""
import math

import pytest

from dynamic_components import geometry as g
from dynamic_components.geometry import Box, GeometryError

SIZE = (0.019, 0.56, 2.0)


def _loops(shape):
    for outer, holes in shape.faces:
        yield outer
        yield from holes


def _key(p):
    return tuple(round(c, 9) for c in p)


def assert_closed_and_oriented(shape):
    """Every directed edge appears once and its reverse once: closed, and
    all faces turn the same way (outward)."""
    directed = {}
    for loop in _loops(shape):
        for i, a in enumerate(loop):
            b = loop[(i + 1) % len(loop)]
            key = (_key(a), _key(b))
            directed[key] = directed.get(key, 0) + 1
    for (a, b), count in directed.items():
        assert count == 1, f"edge {a}->{b} used {count} times"
        assert directed.get((b, a)) == 1, f"edge {a}->{b} has no partner"


def volume(shape):
    """Divergence theorem over all loops (holes are wound the other way, so
    they subtract by themselves)."""
    total = 0.0
    for outer, holes in shape.faces:
        q = outer[0]
        for loop in [outer, *holes]:
            for i, a in enumerate(loop):
                b = loop[(i + 1) % len(loop)]
                total += (q[0] * (a[1] * b[2] - a[2] * b[1])
                          - q[1] * (a[0] * b[2] - a[2] * b[0])
                          + q[2] * (a[0] * b[1] - a[1] * b[0])) / 6.0
    return total


def polygon_area(n, r):
    return 0.5 * n * r * r * math.sin(2 * math.pi / n)


def test_plain_board_is_a_closed_box():
    shape = g.board(SIZE)
    assert len(shape.faces) == 6 and not shape.soft and not shape.issues
    assert_closed_and_oriented(shape)
    assert volume(shape) == pytest.approx(0.019 * 0.56 * 2.0)


def test_origin_moves_the_box():
    shape = g.board((1, 2, 3), origin=(-1, 5, 0.5))
    xs = [p[0] for loop in _loops(shape) for p in loop]
    ys = [p[1] for loop in _loops(shape) for p in loop]
    assert min(xs) == -1 and max(xs) == 0 and min(ys) == 5 and max(ys) == 7
    assert volume(shape) == pytest.approx(6.0)


def test_blind_round_hole_from_the_inner_face():
    cut = Box((0.007, 0.1, 0.1), (0.020, 0.105, 0.105))      # sticks out 1 mm
    shape = g.board(SIZE, cuts=[cut])
    assert not shape.issues
    assert_closed_and_oriented(shape)
    assert len(shape.faces) == 6 + 12 + 1                     # walls + bottom
    assert len(shape.soft) == 12
    expected = 0.019 * 0.56 * 2.0 - polygon_area(12, 0.0025) * 0.012
    assert volume(shape) == pytest.approx(expected, rel=1e-12)


def test_blind_hole_from_the_lower_face():
    cut = Box((-0.001, 0.1, 0.1), (0.012, 0.105, 0.105))
    shape = g.board(SIZE, cuts=[cut])
    assert_closed_and_oriented(shape)
    expected = 0.019 * 0.56 * 2.0 - polygon_area(12, 0.0025) * 0.012
    assert volume(shape) == pytest.approx(expected, rel=1e-12)


@pytest.mark.parametrize("axis", [0, 1, 2])
def test_through_holes_along_every_axis(axis):
    size = (0.4, 0.5, 0.6)
    lo, hi = [0.1, 0.1, 0.1], [0.13, 0.13, 0.13]
    lo[axis], hi[axis] = -0.01, size[axis] + 0.01
    shape = g.board(size, cuts=[Box(tuple(lo), tuple(hi), g.RECT)])
    assert_closed_and_oriented(shape)
    assert len(shape.faces) == 6 + 4
    assert volume(shape) == pytest.approx(0.4 * 0.5 * 0.6 - 0.03 * 0.03 * size[axis])


def test_rectangular_pocket():
    cut = Box((0.1, 0.1, 0.59), (0.2, 0.15, 0.7))
    shape = g.board((0.4, 0.5, 0.6), cuts=[cut])
    assert_closed_and_oriented(shape)
    assert not shape.soft
    assert volume(shape) == pytest.approx(0.4 * 0.5 * 0.6 - 0.1 * 0.05 * 0.01)


def test_square_cutter_is_round_unless_said_otherwise():
    square = ((0.1, 0.1, 0.5), (0.13, 0.13, 0.7))
    assert len(g.board((0.4, 0.5, 0.6), cuts=[Box(*square)]).soft) == 24
    assert not g.board((0.4, 0.5, 0.6), cuts=[Box(*square, g.RECT)]).soft


def test_round_kind_needs_a_round_section():
    shape = g.board((0.4, 0.5, 0.6), cuts=[Box((0.1, 0.1, 0.5), (0.2, 0.13, 0.7), g.ROUND)])
    assert shape.issues and len(shape.faces) == 6


def test_a_raster_of_holes_stays_closed():
    cuts = [Box((0.007, y - 0.0025, 0.0285 + k * 0.032 - 0.0025),
                (0.020, y + 0.0025, 0.0285 + k * 0.032 + 0.0025))
            for y in (0.037, 0.485) for k in range(1, 61)]
    shape = g.board(SIZE, cuts=cuts)
    assert not shape.issues
    assert_closed_and_oriented(shape)
    expected = 0.019 * 0.56 * 2.0 - 120 * polygon_area(12, 0.0025) * 0.012
    assert volume(shape) == pytest.approx(expected, rel=1e-12)


@pytest.mark.parametrize("cut, words", [
    (Box((-0.001, -0.01, -0.01), (0.01, 0.05, 0.05)), "edge"),      # notch over a corner
    (Box((0.005, 0.1, 0.1), (0.010, 0.105, 0.105)), "inside"),      # reaches no face
    (Box((0.007, 0.1, 0.1), (0.007, 0.105, 0.105)), "volume"),      # flat
    (Box((1.0, 0.1, 0.1), (1.1, 0.105, 0.105)), "does not reach"),  # misses
])
def test_unusable_cuts_are_reported_and_skipped(cut, words):
    shape = g.board(SIZE, cuts=[cut])
    assert len(shape.faces) == 6
    assert shape.issues and shape.issues[0][0] == 0 and words in shape.issues[0][1]


def test_touching_or_overlapping_cuts_keep_the_first():
    a = Box((0.007, 0.100, 0.1), (0.02, 0.105, 0.105))
    b = Box((0.007, 0.103, 0.1), (0.02, 0.108, 0.105))       # overlaps a
    c = Box((0.007, 0.105, 0.1), (0.02, 0.110, 0.105))       # touches a
    d = Box((0.007, 0.200, 0.1), (0.02, 0.205, 0.105))       # free
    shape = g.board(SIZE, cuts=[a, b, c, d])
    assert [i for i, _m in shape.issues] == [1, 2]
    assert_closed_and_oriented(shape)


def test_holes_from_both_sides_that_meet_are_refused():
    a = Box((0.007, 0.1, 0.1), (0.02, 0.105, 0.105))
    b = Box((-0.001, 0.1, 0.1), (0.012, 0.105, 0.105))       # reaches into a
    shape = g.board(SIZE, cuts=[a, b])
    assert [i for i, _m in shape.issues] == [1]


def test_limits_and_degenerate_input():
    with pytest.raises(GeometryError):
        g.board((0.0, 1.0, 1.0))
    with pytest.raises(GeometryError):
        g.board((float("nan"), 1.0, 1.0))
    with pytest.raises(GeometryError):
        g.board((1, 1, 1), cuts=[Box((0, 0, 0), (1, 1, 1))] * 3, max_cuts=2)
    cuts = [Box((0.1 * i + 0.01, 0.1, 0.9), (0.1 * i + 0.05, 0.14, 1.1)) for i in range(9)]
    with pytest.raises(GeometryError):
        g.board((1, 1, 1), cuts=cuts, max_faces=60)
    shape = g.board((1, 1, 1), cuts=["not a box"])
    assert shape.issues[0][0] == 0


def test_segments_grow_with_the_diameter():
    assert g.segments_for(0.005) == 12 and g.segments_for(0.010) == 12
    assert g.segments_for(0.035) == 24 and g.segments_for(0.08) == 32


def test_messages_are_translatable():
    shape = g.board(SIZE, cuts=[Box((1.0, 0.1, 0.1), (1.1, 0.105, 0.105))])
    msg = shape.issues[0][1]
    assert msg.template == "The cut does not reach the board"
    with pytest.raises(GeometryError) as info:
        g.board((0, 1, 1))
    assert info.value.msg.template == "The board has no volume"


def _groove_board(cuts, size=(0.019, 0.56, 2.0), **kw):
    return g.board(size, cuts=cuts, **kw)


def test_groove_along_the_whole_height_closes_and_has_the_right_volume():
    # 8 mm deep, 8.5 mm wide, from the inner (+x) face, full height
    shape = _groove_board([Box((0.019 - 0.008, 0.5, -0.1), (0.02, 0.5085, 2.1))])
    assert shape.issues == []
    assert_closed_and_oriented(shape)
    assert volume(shape) == pytest.approx(0.019 * 0.56 * 2.0 - 0.008 * 0.0085 * 2.0)


def test_groove_across_a_board_in_the_other_direction():
    shape = _groove_board([Box((-0.1, 0.5, 0.019 - 0.008), (0.7, 0.5085, 0.02))],
                          size=(0.562, 0.56, 0.019))
    assert shape.issues == []
    assert_closed_and_oriented(shape)
    assert volume(shape) == pytest.approx(0.562 * 0.56 * 0.019 - 0.562 * 0.0085 * 0.008)


def test_holes_and_a_groove_in_the_same_face():
    cuts = [Box((0.019 - 0.008, 0.5, -0.1), (0.02, 0.5085, 2.1)),
            Box((0.019 - 0.012, 0.0325, 0.1), (0.02, 0.0375, 0.105)),     # front row
            Box((0.019 - 0.012, 0.5325, 0.1), (0.02, 0.5375, 0.105))]     # behind the groove
    shape = _groove_board(cuts)
    assert shape.issues == []
    assert_closed_and_oriented(shape)


def test_unfit_grooves_and_corner_notches_are_refused():
    corner = Box((0.011, 0.5, 1.9), (0.02, 0.6, 2.1))               # over a corner
    assert g.board(SIZE, cuts=[corner]).issues[0][1].startswith("The cut runs over an edge")
    # a groove that reaches the side of the board across it is a rebate: refused
    touching = Box((0.011, 0.5, -0.1), (0.02, 0.56, 2.1))
    assert "along a whole side" in _groove_board([touching]).issues[0][1]
    # round grooves do not exist; two ways in one board are refused
    assert _groove_board([Box((0.011, 0.5, -0.1), (0.02, 0.5085, 2.1), g.ROUND)]).issues
    across = Box((0.011, -0.1, 1.0), (0.02, 0.7, 1.01))
    two = _groove_board([Box((0.011, 0.5, -0.1), (0.02, 0.5085, 2.1)), across])
    assert len(two.issues) == 1


def test_two_parallel_grooves_make_three_strips():
    cuts = [Box((0.011, 0.1, -0.1), (0.02, 0.108, 2.1)),
            Box((0.011, 0.5, -0.1), (0.02, 0.508, 2.1))]
    shape = _groove_board(cuts)
    assert shape.issues == []
    assert_closed_and_oriented(shape)
    assert volume(shape) == pytest.approx(0.019 * 0.56 * 2.0 - 2 * 0.008 * 0.008 * 2.0)
