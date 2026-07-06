import numpy as np

from app.services.ai.track_media_collector import TrackMediaCollector


def _frame(color_channel: int, width: int) -> np.ndarray:
    frame = np.zeros((120, width, 3), dtype=np.uint8)
    frame[:, :, color_channel] = 200
    return frame


def test_in_out_overlays_captured_at_crossings() -> None:
    collector = TrackMediaCollector()
    single_in = _frame(1, 80)
    fused_in = _frame(1, 240)
    single_out = _frame(2, 80)
    fused_out = _frame(2, 240)

    collector.set_boundary_overlay('gid_test', 'in', 4, single_in, fused_in)
    collector.set_boundary_overlay('gid_test', 'out', 4, single_out, fused_out)

    snap = collector.pop('gid_test')
    assert snap is not None
    assert snap.single_overlay_in_jpeg is not None
    assert snap.single_overlay_out_jpeg is not None
    assert snap.fused_overlay_in_jpeg is not None
    assert snap.fused_overlay_out_jpeg is not None
    assert snap.single_overlay_in_jpeg != snap.single_overlay_out_jpeg
    assert snap.single_overlay_in_camera_id == 4
    assert snap.single_overlay_out_camera_id == 4


def test_latest_frame_fallback_when_no_out_crossing() -> None:
    collector = TrackMediaCollector()
    single_in = _frame(1, 80)
    fused_in = _frame(1, 240)
    collector.set_boundary_overlay('gid_test', 'in', 4, single_in, fused_in)

    # No OUT crossing — latest frames must be retained for fallback encode.
    collector.update_latest_single('gid_test', 4, _frame(2, 80), ts=10.0)
    collector.update_latest_fused('gid_test', _frame(2, 240), ts=10.0)
    collector.update_latest_single('gid_test', 4, _frame(0, 80), ts=20.0)

    snap = collector.pop('gid_test')
    assert snap is not None
    assert snap.single_overlay_out_jpeg is None
    assert snap.single_latest_frame is not None
    assert snap.single_latest_ts == 20.0
    assert snap.single_latest_camera_id == 4
    assert snap.fused_latest_frame is not None


def test_pop_any_merges_crossing_and_latest() -> None:
    collector = TrackMediaCollector()
    collector.set_boundary_overlay('gid_a', 'in', 4, _frame(1, 80), _frame(1, 240))
    collector.update_latest_single('gid_b', 5, _frame(2, 80), ts=99.0)

    merged = collector.pop_any(['gid_a', 'gid_b'])
    assert merged is not None
    assert merged.single_overlay_in_jpeg is not None
    assert merged.single_latest_frame is not None
    assert merged.single_latest_ts == 99.0
