from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from app.services import pipeline_preview
from app.services.ai.frame_synchronizer import FrameSynchronizer
from app.services.ai.multi_frame_reader import TimedFrame


@dataclass(frozen=True)
class FusionMember:
    camera_id: int
    role: str = 'tile'
    priority: int = 0
    layout_x: int = 0
    layout_y: int = 0
    layout_w: int | None = None
    layout_h: int | None = None
    layout_rotation: float = 0
    crop_top: int = 0
    crop_bottom: int = 0
    crop_left: int = 0
    crop_right: int = 0
    enabled: bool = True


@dataclass(frozen=True)
class FusionConfig:
    fusion_mode: str
    canvas_width: int
    canvas_height: int
    members: list[FusionMember]


DEFAULT_FUSED_MAX_WIDTH = 1280
DEFAULT_FUSED_MAX_HEIGHT = 720


def _paste_with_mask(canvas: np.ndarray, image: np.ndarray, x: int, y: int) -> None:
    canvas_h, canvas_w = canvas.shape[:2]
    image_h, image_w = image.shape[:2]
    x1 = max(0, x)
    y1 = max(0, y)
    x2 = min(canvas_w, x + image_w)
    y2 = min(canvas_h, y + image_h)
    if x1 >= x2 or y1 >= y2:
        return

    src_x1 = x1 - x
    src_y1 = y1 - y
    src = image[src_y1:src_y1 + (y2 - y1), src_x1:src_x1 + (x2 - x1)]
    mask = np.any(src > 0, axis=2)
    canvas_slice = canvas[y1:y2, x1:x2]
    canvas_slice[mask] = src[mask]


class FrameFuser:
    def __init__(self, config: FusionConfig) -> None:
        self._config = config
        self._members = sorted(
            [member for member in config.members if member.enabled],
            key=lambda member: member.priority,
        )

    def fuse(self, frames: dict[int, TimedFrame]) -> np.ndarray:
        canvas = np.zeros(
            (self._config.canvas_height, self._config.canvas_width, 3),
            dtype=np.uint8,
        )
        return self._fuse_layout(canvas, frames)

    def _fuse_layout(self, canvas: np.ndarray, frames: dict[int, TimedFrame]) -> np.ndarray:
        for member in self._members:
            timed_frame = frames.get(member.camera_id)
            if timed_frame is None:
                continue
            frame = timed_frame.frame
            width = member.layout_w or frame.shape[1]
            height = member.layout_h or frame.shape[0]
            resized = cv2.resize(frame, (int(width), int(height)))
            cropped = _crop_frame(resized, member)
            rotated = _rotate_bound(cropped, member.layout_rotation)
            _paste_with_mask(canvas, rotated, member.layout_x, member.layout_y)
        return canvas

class FrameFusionWorker(threading.Thread):
    def __init__(
        self,
        synchronizer: FrameSynchronizer,
        fuser: FrameFuser,
        output_queue: 'queue.Queue',
        stop_event: threading.Event,
        target_fps: float,
    ) -> None:
        super().__init__(daemon=True)
        self._synchronizer = synchronizer
        self._fuser = fuser
        self._output_queue = output_queue
        self._stop_event = stop_event
        self._interval = 1.0 / max(1.0, float(target_fps))

    def run(self) -> None:
        next_emit = time.monotonic()
        while not self._stop_event.is_set():
            now = time.monotonic()
            if now < next_emit:
                time.sleep(min(0.02, next_emit - now))
                continue
            next_emit = now + self._interval
            batch = self._synchronizer.next_batch()
            if not batch:
                continue
            fused = self._fuser.fuse(batch)
            pipeline_preview.push_bgr_frame(fused)
            try:
                self._output_queue.put_nowait(fused)
            except queue.Full:
                try:
                    self._output_queue.get_nowait()
                except queue.Empty:
                    pass
                try:
                    self._output_queue.put_nowait(fused)
                except queue.Full:
                    pass


def _rotate_bound(image: np.ndarray, angle: float) -> np.ndarray:
    if abs(float(angle)) < 0.01:
        return image
    height, width = image.shape[:2]
    center = (width / 2.0, height / 2.0)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    cos = abs(matrix[0, 0])
    sin = abs(matrix[0, 1])
    new_width = int((height * sin) + (width * cos))
    new_height = int((height * cos) + (width * sin))
    matrix[0, 2] += (new_width / 2.0) - center[0]
    matrix[1, 2] += (new_height / 2.0) - center[1]
    return cv2.warpAffine(image, matrix, (new_width, new_height))


def _crop_frame(frame: np.ndarray, member: FusionMember) -> np.ndarray:
    height, width = frame.shape[:2]
    left = min(max(0, int(member.crop_left or 0)), max(0, width - 1))
    right = min(max(0, int(member.crop_right or 0)), max(0, width - left - 1))
    top = min(max(0, int(member.crop_top or 0)), max(0, height - 1))
    bottom = min(max(0, int(member.crop_bottom or 0)), max(0, height - top - 1))
    cropped = frame[top:height - bottom, left:width - right]
    return cropped if cropped.size > 0 else frame


def scaled_fusion_config(
    config: FusionConfig,
    max_width: int = DEFAULT_FUSED_MAX_WIDTH,
    max_height: int = DEFAULT_FUSED_MAX_HEIGHT,
) -> FusionConfig:
    scale = resolve_fusion_scale(config.canvas_width, config.canvas_height, max_width, max_height)
    if abs(scale - 1.0) < 1e-6:
        return config
    return FusionConfig(
        fusion_mode=config.fusion_mode,
        canvas_width=max(1, int(round(config.canvas_width * scale))),
        canvas_height=max(1, int(round(config.canvas_height * scale))),
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
                crop_top=member.crop_top,
                crop_bottom=member.crop_bottom,
                crop_left=member.crop_left,
                crop_right=member.crop_right,
                enabled=member.enabled,
            )
            for member in config.members
        ],
    )


def resolve_fusion_scale(
    canvas_width: int,
    canvas_height: int,
    max_width: int = DEFAULT_FUSED_MAX_WIDTH,
    max_height: int = DEFAULT_FUSED_MAX_HEIGHT,
) -> float:
    if canvas_width <= 0 or canvas_height <= 0:
        return 1.0
    return min(
        1.0,
        max(1, int(max_width)) / float(canvas_width),
        max(1, int(max_height)) / float(canvas_height),
    )


def build_fusion_config_from_group(
    group: Any,
    max_width: int | None = None,
    max_height: int | None = None,
) -> FusionConfig:
    config = FusionConfig(
        fusion_mode=str(group.fusion_mode or 'layout'),
        canvas_width=int(group.canvas_width or 1920),
        canvas_height=int(group.canvas_height or 1080),
        members=[
            FusionMember(
                camera_id=int(member.camera_id),
                role=str(member.role or 'tile'),
                priority=int(member.priority or 0),
                layout_x=int(member.layout_x or 0),
                layout_y=int(member.layout_y or 0),
                layout_w=member.layout_w,
                layout_h=member.layout_h,
                layout_rotation=float(member.layout_rotation or 0),
                crop_top=int(getattr(member, 'crop_top', 0) or 0),
                crop_bottom=int(getattr(member, 'crop_bottom', 0) or 0),
                crop_left=int(getattr(member, 'crop_left', 0) or 0),
                crop_right=int(getattr(member, 'crop_right', 0) or 0),
                enabled=bool(member.enabled),
            )
            for member in group.members
        ],
    )
    if max_width is None or max_height is None:
        return config
    return scaled_fusion_config(config, max_width=max_width, max_height=max_height)
