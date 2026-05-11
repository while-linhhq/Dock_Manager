from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import cv2
import numpy as np

from app.schemas.camera_group import FusedPreviewRequest
from app.services.ai.frame_fusion import FrameFuser, FusionConfig, FusionMember
from app.services.editor_preview import editor_preview_manager

PREVIEW_MAX_WIDTH = 1600
PREVIEW_MAX_HEIGHT = 900


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


def _resolve_preview_scale(canvas_width: int, canvas_height: int) -> float:
    if canvas_width <= 0 or canvas_height <= 0:
        return 1.0
    return min(
        1.0,
        PREVIEW_MAX_WIDTH / float(canvas_width),
        PREVIEW_MAX_HEIGHT / float(canvas_height),
    )


def _scale_homography(homography: list[list[float]] | None, scale: float) -> list[list[float]] | None:
    if homography is None or abs(scale - 1.0) < 1e-6:
        return homography
    scale_matrix = np.array(
        [
            [scale, 0.0, 0.0],
            [0.0, scale, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    matrix = np.array(homography, dtype=np.float64)
    return (scale_matrix @ matrix).astype(float).tolist()


def _build_preview_fuser(data: FusedPreviewRequest) -> _PreviewFuser:
    scale = _resolve_preview_scale(data.canvas_width, data.canvas_height)
    canvas_width = max(1, int(round(data.canvas_width * scale)))
    canvas_height = max(1, int(round(data.canvas_height * scale)))
    fuser = FrameFuser(
        FusionConfig(
            fusion_mode=data.fusion_mode,
            canvas_width=canvas_width,
            canvas_height=canvas_height,
            stitch_metadata=data.stitch_metadata,
            members=[
                FusionMember(
                    camera_id=member.camera_id,
                    role=member.role,
                    priority=member.priority,
                    layout_x=int(round(member.layout_x * scale)),
                    layout_y=int(round(member.layout_y * scale)),
                    layout_w=max(1, int(round(member.layout_w * scale))) if member.layout_w else None,
                    layout_h=max(1, int(round(member.layout_h * scale))) if member.layout_h else None,
                    layout_rotation=member.layout_rotation,
                    homography=_scale_homography(member.homography, scale),
                    enabled=member.enabled,
                )
                for member in data.members
            ],
        )
    )
    return _PreviewFuser(fuser=fuser, scale=scale)
