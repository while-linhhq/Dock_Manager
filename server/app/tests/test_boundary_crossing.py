from app.services.ai.boundary_crossing import (
    BoundaryConfig,
    BoundaryCrossingTracker,
    segment_intersection_t,
)


def test_crossing_returns_param_when_segments_cross():
    t = segment_intersection_t((0, 5), (10, 5), (5, 0, 5, 10))
    assert t is not None and 0.0 <= t <= 1.0


def test_no_crossing_returns_none():
    assert segment_intersection_t((0, 0), (1, 1), (5, 0, 5, 10)) is None


def _cfg():
    return BoundaryConfig(
        frame_w=100,
        frame_h=100,
        line1=[(30, 0), (30, 100)],
        line2=[(60, 0), (60, 100)],
        enabled=True,
    )


def test_in_when_line1_then_line2():
    trk = BoundaryCrossingTracker(_cfg())
    assert trk.update('a', (10, 50), 1.0, 100, 100) is None
    assert trk.update('a', (40, 50), 2.0, 100, 100) is None
    assert trk.update('a', (70, 50), 3.0, 100, 100) == 'in'


def test_out_when_line2_then_line1():
    trk = BoundaryCrossingTracker(_cfg())
    trk.update('b', (70, 50), 1.0, 100, 100)
    trk.update('b', (50, 50), 2.0, 100, 100)
    assert trk.update('b', (10, 50), 3.0, 100, 100) == 'out'


def test_scales_lines_to_frame():
    trk = BoundaryCrossingTracker(_cfg())
    trk.update('c', (10, 50), 1.0, 200, 200)
    trk.update('c', (80, 50), 2.0, 200, 200)
    assert trk.update('c', (140, 50), 3.0, 200, 200) == 'in'


def test_polyline_crossing_uses_any_segment():
    cfg = BoundaryConfig(
        frame_w=100,
        frame_h=100,
        line1=[(10, 50), (30, 50), (30, 100)],
        line2=[(70, 0), (70, 100)],
        enabled=True,
    )
    trk = BoundaryCrossingTracker(cfg)
    trk.update('d', (5, 50), 1.0, 100, 100)
    trk.update('d', (25, 50), 2.0, 100, 100)
    assert trk.update('d', (80, 50), 3.0, 100, 100) == 'in'
