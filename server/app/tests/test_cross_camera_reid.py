"""Cross-camera re-id: plate must not leak to a second concurrent boat via visual match."""

import time

import numpy as np

from app.services.ai.boat_tracker import TrackState, TrackedBoat
from app.services.ai.cross_camera_reid import CrossCameraReIdManager


def _track(
    track_id: str,
    *,
    camera_id: int = 1,
    box: tuple[float, float, float, float] = (10.0, 10.0, 100.0, 100.0),
) -> TrackedBoat:
    now = time.time()
    return TrackedBoat(
        track_id=track_id,
        state=TrackState.CONFIRMED,
        box=np.array(box, dtype=np.float32),
        conf=0.9,
        hits=5,
        misses=0,
        first_seen_ts=now,
        last_seen_ts=now,
        camera_id=camera_id,
    )


def _unit_embedding(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    vec = rng.standard_normal(128).astype(np.float32)
    return vec / (np.linalg.norm(vec) + 1e-6)


def test_visual_match_does_not_propagate_plate_without_ocr() -> None:
    mgr = CrossCameraReIdManager([1, 2, 3], visual_threshold=0.5, handoff_window_sec=60.0)
    emb = _unit_embedding(7)

    boat_a = _track('trk_a', camera_id=2)
    mgr.report_track_update(2, boat_a, embedding=emb)
    mgr.report_ocr_result(2, 'trk_a', 'SG-6375', 0.95)

    boat_b = _track('trk_b', camera_id=3, box=(200.0, 200.0, 320.0, 320.0))
    similar_emb = emb * 0.98 + _unit_embedding(99) * 0.02
    mgr.report_track_update(3, boat_b, embedding=similar_emb)

    assert mgr.get_global_ship_id(3, 'trk_b') is None
    assert boat_b.ship_id is None


def test_ocr_on_second_track_shows_plate_only_after_read() -> None:
    mgr = CrossCameraReIdManager([1, 2], visual_threshold=0.5, handoff_window_sec=60.0)
    emb = _unit_embedding(3)

    mgr.report_track_update(1, _track('trk_1', camera_id=1), embedding=emb)
    mgr.report_ocr_result(1, 'trk_1', 'SG-7082', 0.9)

    mgr.report_track_update(2, _track('trk_2', camera_id=2), embedding=emb)
    assert mgr.get_global_ship_id(2, 'trk_2') is None

    mgr.report_ocr_result(2, 'trk_2', 'SG-7082', 0.85)
    assert mgr.get_global_ship_id(2, 'trk_2') == 'SG-7082'


def test_handoff_inherits_plate_after_source_track_removed() -> None:
    mgr = CrossCameraReIdManager([1, 2], visual_threshold=0.5, handoff_window_sec=60.0)
    emb = _unit_embedding(11)

    boat_a = _track('trk_cam1', camera_id=1)
    mgr.report_track_update(1, boat_a, embedding=emb)
    mgr.report_ocr_result(1, 'trk_cam1', 'SG-1111', 0.92)
    mgr.report_track_removed(1, boat_a, ocr_history=[('SG-1111', 0.92)])

    boat_b = _track('trk_cam2', camera_id=2)
    mgr.report_track_update(2, boat_b, embedding=emb)

    assert mgr.get_global_ship_id(2, 'trk_cam2') == 'SG-1111'


def test_same_plate_merge_skipped_when_both_cameras_active() -> None:
    mgr = CrossCameraReIdManager([1, 2], visual_threshold=0.9, handoff_window_sec=60.0)

    mgr.report_track_update(1, _track('trk_x', camera_id=1))
    mgr.report_ocr_result(1, 'trk_x', 'SG-6375', 0.9)

    mgr.report_track_update(2, _track('trk_y', camera_id=2))
    mgr.report_ocr_result(2, 'trk_y', 'SG-6375', 0.88)

    gid_x = mgr._track_to_global[(1, 'trk_x')]
    gid_y = mgr._track_to_global[(2, 'trk_y')]
    assert gid_x != gid_y
