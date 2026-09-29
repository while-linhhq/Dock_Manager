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
