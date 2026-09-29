"""Cờ cấu hình runtime phải chảy tới đúng thành phần xử lý trong PerCameraPipeline."""
from __future__ import annotations

import queue
import threading

from app.services.ai.per_camera_pipeline import PerCameraPipeline, PerCameraPipelineConfig


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


def _build_pipeline(config: PerCameraPipelineConfig) -> PerCameraPipeline:
    return PerCameraPipeline(
        config=config,
        detector=object(),
        detector_lock=threading.Lock(),
        reid_manager=object(),
        embedding_extractor=object(),
        video_queue=None,
        stop_event=threading.Event(),
        ocr_cache={},
        ocr_lock=threading.RLock(),
        runs_base='/tmp',
        input_frame_queue=queue.Queue(),
    )


def test_clahe_fast_defaults_true() -> None:
    pipeline = _build_pipeline(_pipeline_config())

    assert pipeline._clahe_config.fast is True


def test_clahe_fast_false_reaches_preprocessor() -> None:
    pipeline = _build_pipeline(_pipeline_config(clahe_fast=False))

    assert pipeline._clahe_config.fast is False


class _FakeDetector:
    """Detector giả trả box trong hệ toạ độ của frame đưa vào."""

    def __init__(self, boxes: list[list[float]] | None = None) -> None:
        self.boxes = boxes or []
        self.frames: list = []

    def predict_boxes(self, frame):
        self.frames.append(frame)
        return [list(box) for box in self.boxes], [0.9] * len(self.boxes)


def _build_pipeline_with_detector(config: PerCameraPipelineConfig, detector) -> PerCameraPipeline:
    return PerCameraPipeline(
        config=config,
        detector=detector,
        detector_lock=threading.Lock(),
        reid_manager=object(),
        embedding_extractor=object(),
        video_queue=None,
        stop_event=threading.Event(),
        ocr_cache={},
        ocr_lock=threading.RLock(),
        runs_base='/tmp',
        input_frame_queue=queue.Queue(),
    )


def _frame(height: int = 80, width: int = 120):
    import numpy as np

    return np.full((height, width, 3), 40, dtype=np.uint8)


def test_detect_scale_default_does_not_resize(monkeypatch) -> None:
    import cv2

    calls: list = []
    monkeypatch.setattr(cv2, 'resize', lambda *args, **kwargs: calls.append(kwargs) or _frame())
    detector = _FakeDetector()
    pipeline = _build_pipeline_with_detector(_pipeline_config(), detector)

    pipeline._process_frame(_frame(), 1.0)

    assert calls == []
    assert detector.frames and detector.frames[0].shape == (80, 120, 3)


def test_detect_scale_halves_detect_frame(monkeypatch) -> None:
    import cv2

    calls: list = []
    real_resize = cv2.resize

    def _spy(src, dsize=None, **kwargs):
        calls.append(kwargs)
        factor = kwargs.get('fx', 1.0)
        return real_resize(src, dsize, **kwargs) if dsize else real_resize(
            src, (int(src.shape[1] * factor), int(src.shape[0] * factor)), interpolation=kwargs.get('interpolation', cv2.INTER_LINEAR)
        )

    monkeypatch.setattr(cv2, 'resize', _spy)
    detector = _FakeDetector()
    pipeline = _build_pipeline_with_detector(_pipeline_config(detect_scale=0.5), detector)

    pipeline._process_frame(_frame(), 1.0)

    assert calls and calls[0].get('fx') == 0.5
    assert detector.frames[0].shape == (40, 60, 3)


def test_detect_scale_maps_boxes_back_to_full_res(monkeypatch) -> None:
    captured: list = []
    # Box 100x100 ở hệ detect → 200x200 ở full-res, lớn hơn ngưỡng lọc 50x30.
    detector = _FakeDetector(boxes=[[100.0, 100.0, 200.0, 200.0]])
    pipeline = _build_pipeline_with_detector(_pipeline_config(detect_scale=0.5), detector)
    monkeypatch.setattr(pipeline._tracker, 'update', lambda boxes, confs: captured.append(boxes) or [])

    pipeline._process_frame(_frame(height=800, width=1200), 1.0)

    assert captured and captured[0] == [[200.0, 200.0, 400.0, 400.0]]


def test_crop_box_clamps_at_scale_one() -> None:
    pipeline = _build_pipeline(_pipeline_config())

    assert pipeline._crop_box_for_track((10.0, 20.0, 30.0, 40.0), 100, 100) == (10, 20, 30, 40)


def test_crop_box_pads_when_scale_below_one() -> None:
    pipeline = _build_pipeline(_pipeline_config(detect_scale=0.5, crop_pad_ratio=0.5))

    assert pipeline._crop_box_for_track((40.0, 40.0, 50.0, 50.0), 100, 100) == (35, 35, 55, 55)
