from app.services.ai.boundary_crossing import (
    BoundaryConfig,
    BoundaryCrossingTracker,
    bbox_fraction_inside_polygon,
    polyline_touches_bbox,
    segment_intersection_t,
)


def test_crossing_returns_param_when_segments_cross():
    t = segment_intersection_t((0, 5), (10, 5), (5, 0, 5, 10))
    assert t is not None and 0.0 <= t <= 1.0


def test_no_crossing_returns_none():
    assert segment_intersection_t((0, 0), (1, 1), (5, 0, 5, 10)) is None


def _zone() -> list[tuple[float, float]]:
    return [(30, 20), (80, 20), (80, 80), (30, 80)]


def _cfg(threshold: float = 0.30) -> BoundaryConfig:
    return BoundaryConfig(
        frame_w=100,
        frame_h=100,
        line1=[(30, 0), (30, 100)],
        line2=[(60, 0), (60, 100)],
        berth_zone=_zone(),
        enabled=True,
        bbox_cross_threshold=threshold,
    )


def test_inside_ratio_fully_outside_polygon():
    ratio = bbox_fraction_inside_polygon((5, 40, 20, 60), _zone())
    assert ratio == 0.0


def test_inside_ratio_fully_inside_polygon():
    ratio = bbox_fraction_inside_polygon((35, 40, 55, 60), _zone())
    assert ratio == 1.0


def test_inside_ratio_straddle_about_half():
    ratio = bbox_fraction_inside_polygon((20, 40, 40, 60), _zone())
    assert 0.45 <= ratio <= 0.55


def test_polyline_touches_bbox_vertical_line():
    assert polyline_touches_bbox([(30, 0), (30, 100)], (25, 45, 35, 55))


def test_polyline_does_not_touch_bbox():
    assert not polyline_touches_bbox([(30, 0), (30, 100)], (5, 45, 15, 55))


def test_in_when_l1_then_l2_and_overlap():
    trk = BoundaryCrossingTracker(_cfg())
    assert trk.update('a', (25, 45, 35, 55), 1.0, 100, 100) is None
    assert trk.update('a', (45, 45, 65, 55), 2.0, 100, 100) == 'in'


def test_no_in_when_l2_before_l1():
    trk = BoundaryCrossingTracker(_cfg())
    trk.update('b', (55, 45, 75, 55), 1.0, 100, 100)
    assert trk.update('b', (25, 45, 35, 55), 2.0, 100, 100) is None


def test_no_in_when_l1_l2_but_low_overlap():
    cfg = BoundaryConfig(
        frame_w=100,
        frame_h=100,
        line1=[(30, 0), (30, 100)],
        line2=[(60, 0), (60, 100)],
        berth_zone=[(55, 20), (65, 20), (65, 80), (55, 80)],
        bbox_cross_threshold=0.90,
    )
    trk = BoundaryCrossingTracker(cfg)
    trk.update('c', (25, 45, 35, 55), 1.0, 100, 100)
    assert trk.update('c', (45, 45, 63, 55), 2.0, 100, 100) is None


def test_out_when_overlap_drops_below_threshold():
    trk = BoundaryCrossingTracker(_cfg())
    trk.update('d', (25, 45, 35, 55), 1.0, 100, 100)
    trk.update('d', (45, 45, 65, 55), 2.0, 100, 100)
    assert trk.update('d', (10, 45, 28, 55), 3.0, 100, 100) == 'out'


def test_completed_track_does_not_emit_second_in():
    trk = BoundaryCrossingTracker(_cfg())
    trk.update('e', (25, 45, 35, 55), 1.0, 100, 100)
    trk.update('e', (45, 45, 65, 55), 2.0, 100, 100)
    trk.update('e', (10, 45, 28, 55), 3.0, 100, 100)
    assert trk.update('e', (45, 45, 65, 55), 4.0, 100, 100) is None


def test_from_dict_requires_berth_zone():
    assert BoundaryConfig.from_dict({
        'enabled': True,
        'frame_w': 100,
        'frame_h': 100,
        'line1': [{'x': 0, 'y': 0}, {'x': 0, 'y': 100}],
        'line2': [{'x': 50, 'y': 0}, {'x': 50, 'y': 100}],
    }) is None

    cfg = BoundaryConfig.from_dict({
        'enabled': True,
        'frame_w': 100,
        'frame_h': 100,
        'line1': [{'x': 0, 'y': 0}, {'x': 0, 'y': 100}],
        'line2': [{'x': 50, 'y': 0}, {'x': 50, 'y': 100}],
        'berth_zone': [{'x': 10, 'y': 10}, {'x': 90, 'y': 10}, {'x': 90, 'y': 90}],
    })
    assert cfg is not None
    assert len(cfg.berth_zone) == 3


def test_for_overlay_allows_missing_berth_zone():
    cfg = BoundaryConfig.for_overlay({
        'enabled': True,
        'frame_w': 100,
        'frame_h': 100,
        'line1': [{'x': 0, 'y': 0}, {'x': 0, 'y': 100}],
        'line2': [{'x': 50, 'y': 0}, {'x': 50, 'y': 100}],
    })
    assert cfg is not None
    assert cfg.berth_zone == []


def test_berth_visual_state_pending_in_out():
    from app.services.ai.boat_tracker import TrackedBoat, TrackState
    from app.utils.ai.overlay import (
        berth_fill_color_for_state,
        draw_berth_state_bbox_overlays,
        resolve_berth_visual_state,
        BERTH_PENDING_FILL_BGR,
    )
    import numpy as np

    box = np.array([10.0, 10.0, 40.0, 40.0], dtype=np.float32)
    track = TrackedBoat(
        track_id='t1',
        state=TrackState.CONFIRMED,
        box=box,
        conf=0.9,
        hits=3,
        misses=0,
        first_seen_ts=0.0,
        last_seen_ts=1.0,
    )
    assert resolve_berth_visual_state(track) == 'pending'
    track.berth_in_ts = 1.0
    assert resolve_berth_visual_state(track) == 'in'
    track.berth_out_ts = 2.0
    assert resolve_berth_visual_state(track) == 'out'
    assert berth_fill_color_for_state('pending') == BERTH_PENDING_FILL_BGR

    frame = np.zeros((80, 80, 3), dtype=np.uint8)
    track.berth_in_ts = None
    track.berth_out_ts = None
    draw_berth_state_bbox_overlays(frame, [track])
    assert frame[20, 20].any()


def test_zone_overlap_ratio_public_api_matches_internal_geometry():
    trk = BoundaryCrossingTracker(_cfg(threshold=0.30))
    # bbox fully inside zone -> ~100%
    ratio = trk.zone_overlap_ratio((35, 40, 55, 60), frame_w=100, frame_h=100)
    assert ratio >= 0.99

    # bbox fully outside -> 0%
    ratio_out = trk.zone_overlap_ratio((5, 40, 20, 60), frame_w=100, frame_h=100)
    assert ratio_out == 0.0

    assert trk.config.bbox_cross_threshold == 0.30


def test_inside_ratio_cw_polygon_matches_ccw():
    inside_box = (35, 40, 55, 60)
    ccw_ratio = bbox_fraction_inside_polygon(inside_box, _zone())
    cw_ratio = bbox_fraction_inside_polygon(inside_box, list(reversed(_zone())))
    assert ccw_ratio >= 0.99
    assert cw_ratio >= 0.99


def test_zone_overlap_when_live_frame_differs_from_config():
    """BBox is in live RTSP pixels; only berth_zone is scaled from config frame."""
    trk = BoundaryCrossingTracker(_cfg(threshold=0.30))
    # Config zone x=30..80, y=20..80 on 100x100 -> on 200x200: x=60..160, y=40..160
    ratio = trk.zone_overlap_ratio((70, 80, 110, 120), frame_w=200, frame_h=200)
    assert ratio >= 0.99

    ratio_out = trk.zone_overlap_ratio((10, 80, 40, 120), frame_w=200, frame_h=200)
    assert ratio_out == 0.0


def test_zone_overlap_diagonal_berth_polygon_camera_bachdang_2():
    """Regression: diagonal berth_zone must not clip to 0% (tangent-as-normal bug)."""
    cfg = BoundaryConfig(
        frame_w=2560,
        frame_h=1440,
        line1=[(3, 804), (1782, 379), (2393, 657)],
        line2=[(3, 818), (1779, 403), (2379, 670)],
        berth_zone=[
            (3, 808),
            (1782, 393),
            (2543, 749),
            (2530, 1394),
            (3, 1421),
        ],
        bbox_cross_threshold=0.30,
    )
    trk = BoundaryCrossingTracker(cfg)
    ratio = trk.zone_overlap_ratio((150, 950, 850, 1350), frame_w=2560, frame_h=1440)
    assert ratio >= 0.99
