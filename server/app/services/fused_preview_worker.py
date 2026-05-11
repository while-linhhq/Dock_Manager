from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import cv2

from app.schemas.camera_group import FusedPreviewRequest
from app.services.ai.frame_fusion import FrameFuser, FusionConfig, FusionMember, scaled_fusion_config
from app.services.editor_preview import editor_preview_manager

PREVIEW_MAX_WIDTH = 1280
PREVIEW_MAX_HEIGHT = 720


@dataclass(frozen=True)
class _PreviewFuser:
    fuser: FrameFuser
    scale: float


class FusedPreviewWorker(threading.Thread):
    def __init__(self, target_fps: float, jpeg_quality: int = 72) -> None:
        super().__init__(daemon=True)
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._jpeg_ready = threading.Condition(self._lock)
        self._interval = 1.0 / max(1.0, float(target_fps))
        self._jpeg_quality = jpeg_quality
        self._config: FusedPreviewRequest | None = None
        self._config_key: str | None = None
        self._preview_fuser: _PreviewFuser | None = None
        self._latest_jpeg: bytes | None = None
        self._sequence = 0
        self._last_frame_signature: tuple[tuple[int, int], ...] | None = None

    def stop(self) -> None:
        self._stop_event.set()
        with self._jpeg_ready:
            self._jpeg_ready.notify_all()

    def update_config(self, config: FusedPreviewRequest) -> None:
        config_key = config.model_dump_json()
        with self._lock:
            self._config = config
            if config_key != self._config_key:
                self._config_key = config_key
                self._preview_fuser = _build_preview_fuser(config)
                self._last_frame_signature = None

    def wait_for_jpeg(
        self,
        last_sequence: int,
        timeout: float = 1.0,
    ) -> tuple[int, bytes | None]:
        with self._jpeg_ready:
            self._jpeg_ready.wait_for(
                lambda: self._stop_event.is_set() or self._sequence > last_sequence,
                timeout=timeout,
            )
            if self._sequence <= last_sequence:
                return last_sequence, None
            return self._sequence, self._latest_jpeg

    def run(self) -> None:
        next_emit = time.monotonic()
        while not self._stop_event.is_set():
            now = time.monotonic()
            if now < next_emit:
                self._stop_event.wait(min(0.05, next_emit - now))
                continue
            next_emit = now + self._interval

            with self._lock:
                config = self._config
                preview_fuser = self._preview_fuser

            if config is None or preview_fuser is None:
                self._stop_event.wait(0.05)
                continue

            frame_ids = [member.camera_id for member in config.members if member.enabled]
            frames = editor_preview_manager.latest_frames(frame_ids, copy_frames=False)
            if not frames:
                continue
            frame_signature = tuple(
                sorted((camera_id, timed_frame.sequence) for camera_id, timed_frame in frames.items())
            )
            if frame_signature == self._last_frame_signature:
                continue
            self._last_frame_signature = frame_signature

            fused = preview_fuser.fuser.fuse(frames)
            ok, encoded = cv2.imencode(
                '.jpg',
                fused,
                [int(cv2.IMWRITE_JPEG_QUALITY), self._jpeg_quality],
            )
            if not ok:
                continue

            with self._jpeg_ready:
                self._latest_jpeg = encoded.tobytes()
                self._sequence += 1
                self._jpeg_ready.notify_all()


def _build_preview_fuser(data: FusedPreviewRequest) -> _PreviewFuser:
    base_config = FusionConfig(
        fusion_mode=data.fusion_mode,
        canvas_width=data.canvas_width,
        canvas_height=data.canvas_height,
        members=[
            FusionMember(
                camera_id=member.camera_id,
                role=member.role,
                priority=member.priority,
                layout_x=member.layout_x,
                layout_y=member.layout_y,
                layout_w=member.layout_w,
                layout_h=member.layout_h,
                layout_rotation=member.layout_rotation,
                crop_top=member.crop_top,
                crop_bottom=member.crop_bottom,
                crop_left=member.crop_left,
                crop_right=member.crop_right,
                enabled=member.enabled,
            )
            for member in data.members
        ],
    )
    scaled_config = scaled_fusion_config(
        base_config,
        max_width=PREVIEW_MAX_WIDTH,
        max_height=PREVIEW_MAX_HEIGHT,
    )
    scale = scaled_config.canvas_width / max(1, data.canvas_width)
    return _PreviewFuser(
        fuser=FrameFuser(scaled_config),
        scale=scale,
    )
