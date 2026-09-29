"""Overlay chỉ được dựng khi có consumer thật, và frame gốc không bị sửa.

Trước đây `_process_frame` luôn copy frame full-res rồi vẽ overlay, kể cả khi
không bật preview stream, không ghi video và không có callback media nào.
"""
from __future__ import annotations

import queue
import threading

import numpy as np
import pytest

from app.services.ai import per_camera_pipeline as pipeline_module
from app.services.ai.boat_tracker import TrackState
from app.services.ai.per_camera_pipeline import PerCameraPipeline, PerCameraPipelineConfig


class _FakeDetector:
    def predict_boxes(self, frame):
        return [], []


class _StubTrack:
    """Chỉ cần đúng thuộc tính mà `_needs_overlay_frame` đọc."""

    def __init__(self, state: TrackState) -> None:
        self.state = state


def _pipeline_config(**overrides) -> PerCameraPipelineConfig:
    base = dict(
        camera_id=1,
        source='rtsp://example/stream',
        record_fps=1.0,
        enable_ocr=False,
        ocr_interval_sec=1.0,
        ocr_label_ttl_sec=1.0,
        save_min_interval_sec=1.0,
        ocr_audit_save_frames=False,
        resize_scale=0.5,
        track_iou_threshold=0.3,
        track_reid_window_sec=1.0,
        track_reid_max_dist=1.0,
        track_min_confirm_sec=1.0,
        track_max_tentative_sec=1.0,
        track_max_lost_sec=1.0,
        clahe_clip_limit=3.0,
        clahe_tile_size=8,
        clahe_enable_gray_world=True,
        edge_zone_ratio=0.1,
    )
    base.update(overrides)
    return PerCameraPipelineConfig(**base)


def _build_pipeline(config: PerCameraPipelineConfig, **kwargs) -> PerCameraPipeline:
    kwargs.setdefault('video_queue', None)
    return PerCameraPipeline(
        config=config,
        detector=_FakeDetector(),
        detector_lock=threading.Lock(),
        reid_manager=object(),
        embedding_extractor=object(),
        stop_event=threading.Event(),
        ocr_cache={},
        ocr_lock=threading.RLock(),
        runs_base='/tmp',
        input_frame_queue=queue.Queue(),
        **kwargs,
    )


@pytest.fixture
def draw_calls(monkeypatch) -> list:
    calls: list = []

    def _fake_draw(display_frame, tracked_boats, ocr_cache, ocr_lock, ocr_label_ttl, fps, resize_scale, **kwargs):
        calls.append({'shape': display_frame.shape, 'resize_scale': resize_scale})
        return display_frame

    monkeypatch.setattr(pipeline_module, 'draw_ship_detection_overlay', _fake_draw)
    monkeypatch.setattr(pipeline_module.pipeline_preview, 'push_bgr_frame', lambda frame: None)
    return calls


def _frame() -> np.ndarray:
    return np.full((80, 120, 3), 40, dtype=np.uint8)


def test_overlay_not_drawn_without_consumers(draw_calls) -> None:
    pipeline = _build_pipeline(_pipeline_config(enable_preview_stream=False))
    frame = _frame()
    original = frame.copy()

    pipeline._process_frame(frame, 1.0)

    assert draw_calls == []
    assert np.array_equal(frame, original)


def test_overlay_drawn_for_preview_stream(draw_calls) -> None:
    pipeline = _build_pipeline(_pipeline_config(enable_preview_stream=True))

    pipeline._process_frame(_frame(), 1.0)

    assert len(draw_calls) == 1
    assert draw_calls[0]['resize_scale'] == 0.5


def test_overlay_drawn_for_video_queue(draw_calls) -> None:
    pipeline = _build_pipeline(_pipeline_config(), video_queue=queue.Queue(maxsize=1))

    pipeline._process_frame(_frame(), 1.0)

    assert len(draw_calls) == 1


def test_needs_overlay_frame_matrix() -> None:
    assert _build_pipeline(_pipeline_config())._needs_overlay_frame([]) is False
    assert _build_pipeline(_pipeline_config(enable_preview_stream=True))._needs_overlay_frame([]) is True
    assert (
        _build_pipeline(_pipeline_config(), video_queue=queue.Queue(maxsize=1))._needs_overlay_frame([])
        is True
    )

    with_callback = _build_pipeline(_pipeline_config(), on_boundary_media_sample=lambda *args: None)
    assert with_callback._needs_overlay_frame([]) is False
    assert with_callback._needs_overlay_frame([_StubTrack(TrackState.TENTATIVE)]) is False
    assert with_callback._needs_overlay_frame([_StubTrack(TrackState.CONFIRMED)]) is True
