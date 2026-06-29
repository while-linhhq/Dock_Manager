"""Tests for zone-gated identity vote (per_camera_pipeline._is_in_recognition_zone)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.ai.boat_tracker import BoatTracker, TrackedBoat, TrackState
from app.services.ai.per_camera_pipeline import PerCameraPipeline, PerCameraPipelineConfig


def _make_pipeline() -> PerCameraPipeline:
    cfg = PerCameraPipelineConfig(
        camera_id=1,
        source='rtsp://test',
        record_fps=25.0,
        enable_ocr=True,
        ocr_interval_sec=1.0,
        ocr_label_ttl_sec=5.0,
        save_min_interval_sec=1.0,
        ocr_audit_save_frames=False,
        resize_scale=1.0,
        track_iou_threshold=0.3,
        track_reid_window_sec=120.0,
        track_reid_max_dist=150.0,
        track_min_confirm_sec=2.0,
        track_max_tentative_sec=5.0,
        track_max_lost_sec=10.0,
        clahe_clip_limit=2.0,
        clahe_tile_size=8,
        edge_zone_ratio=0.05,
    )
    pipeline = PerCameraPipeline.__new__(PerCameraPipeline)
    pipeline.config = cfg
    pipeline._tracker = BoatTracker(camera_id=1)
    pipeline._reid_manager = MagicMock()
    pipeline._reid_manager.report_ocr_result = MagicMock()
    pipeline._reid_manager.get_global_ship_id = MagicMock(return_value=None)
    pipeline._ocr_cache = {}
    pipeline._ocr_lock = __import__('threading').RLock()
    pipeline._ship_id_catalog = None
    pipeline._ship_id_rule_engine = None
    return pipeline


def _inject_track(pipeline: PerCameraPipeline, track_id: str, overlap, threshold) -> None:
    """Directly insert a minimal TrackedBoat into the tracker's _tracks dict."""
    import numpy as np
    import time
    now = time.monotonic()
    tb = TrackedBoat(
        track_id=track_id,
        state=TrackState.CONFIRMED,
        box=np.array([10.0, 10.0, 60.0, 60.0]),
        conf=0.9,
        hits=3,
        misses=0,
        first_seen_ts=now,
        last_seen_ts=now,
        camera_id=1,
        berth_zone_overlap=overlap,
        berth_zone_threshold=threshold,
    )
    with pipeline._tracker._lock:
        pipeline._tracker._tracks[track_id] = tb


# --- _is_in_recognition_zone ---

def test_zone_gate_below_threshold():
    """Track with overlap < threshold → not in zone."""
    p = _make_pipeline()
    _inject_track(p, 'trk_1', overlap=0.1, threshold=0.3)
    assert p._is_in_recognition_zone('trk_1') is False


def test_zone_gate_above_threshold():
    """Track with overlap >= threshold → in zone."""
    p = _make_pipeline()
    _inject_track(p, 'trk_2', overlap=0.5, threshold=0.3)
    assert p._is_in_recognition_zone('trk_2') is True


def test_zone_gate_no_zone_configured():
    """Track with no berth zone (None) → always in zone (backward compat)."""
    p = _make_pipeline()
    _inject_track(p, 'trk_3', overlap=None, threshold=None)
    assert p._is_in_recognition_zone('trk_3') is True


def test_zone_gate_track_gone():
    """Non-existent track → returns True (allow last-moment vote)."""
    p = _make_pipeline()
    assert p._is_in_recognition_zone('trk_missing') is True


# --- _on_ocr_result gating ---

def test_ocr_result_gated_when_out_of_zone():
    """OCR vote blocked when track is outside berth zone."""
    p = _make_pipeline()
    _inject_track(p, 'trk_4', overlap=0.05, threshold=0.3)
    p._on_ocr_result('trk_4', 'HQ-12345', 0.9)
    p._reid_manager.report_ocr_result.assert_not_called()


def test_ocr_result_allowed_when_in_zone():
    """OCR vote passes when track is inside berth zone."""
    p = _make_pipeline()
    _inject_track(p, 'trk_5', overlap=0.6, threshold=0.3)
    p._on_ocr_result('trk_5', 'HQ-12345', 0.9)
    p._reid_manager.report_ocr_result.assert_called_once()


# --- pool preserved after leaving zone ---

def test_pool_preserved_after_leaving_zone():
    """Votes accumulated while in zone remain after overlap drops below threshold."""
    p = _make_pipeline()
    _inject_track(p, 'trk_6', overlap=0.6, threshold=0.3)
    # vote while in zone
    p._on_ocr_result('trk_6', 'HQ-99999', 0.8)
    assert p._reid_manager.report_ocr_result.call_count == 1

    # ship leaves zone
    with p._tracker._lock:
        p._tracker._tracks['trk_6'].berth_zone_overlap = 0.05

    # new vote blocked — count stays at 1
    p._on_ocr_result('trk_6', 'HQ-99999', 0.8)
    assert p._reid_manager.report_ocr_result.call_count == 1
