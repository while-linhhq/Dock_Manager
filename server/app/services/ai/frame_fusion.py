from __future__ import annotations

import base64
import queue
import threading
import time
import zlib
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
    homography: list[list[float]] | None = None
    enabled: bool = True


@dataclass(frozen=True)
class FusionConfig:
    fusion_mode: str
    canvas_width: int
    canvas_height: int
    members: list[FusionMember]
    stitch_metadata: dict[str, Any] | None = None


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
        metadata = config.stitch_metadata or {}
        self._exposure_gains = _parse_exposure_gains(metadata.get('exposure_gains'))
        self._stored_blend_weights = _decode_blend_weights(
            metadata.get('blend_weights'),
            metadata.get('blend_weights_shape'),
            config.canvas_width,
            config.canvas_height,
        )

    def fuse(self, frames: dict[int, TimedFrame]) -> np.ndarray:
        canvas = np.zeros(
            (self._config.canvas_height, self._config.canvas_width, 3),
            dtype=np.uint8,
        )
        if self._config.fusion_mode in {'homography', 'panorama'}:
            return self._fuse_homography(canvas, frames)
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
            rotated = _rotate_bound(resized, member.layout_rotation)
            _paste_with_mask(canvas, rotated, member.layout_x, member.layout_y)
        return canvas

    def _fuse_homography(self, canvas: np.ndarray, frames: dict[int, TimedFrame]) -> np.ndarray:
        warped_items: list[tuple[int, np.ndarray, np.ndarray]] = []
        missing_homography: dict[int, TimedFrame] = {}
        canvas_size = (self._config.canvas_width, self._config.canvas_height)

        for member in self._members:
            timed_frame = frames.get(member.camera_id)
            if timed_frame is None:
                continue
            if not member.homography:
                missing_homography[member.camera_id] = timed_frame
                continue

            matrix = np.array(member.homography, dtype=np.float32)
            frame = _apply_exposure_gain(timed_frame.frame, self._exposure_gains.get(member.camera_id, 1.0))
            warped = cv2.warpPerspective(frame, matrix, canvas_size)
            mask = np.any(warped > 0, axis=2).astype(np.uint8)
            if int(mask.sum()) == 0:
                continue
            warped_items.append((member.camera_id, warped, mask))

        if warped_items:
            canvas = _feather_blend(
                warped_items,
                self._stored_blend_weights,
                self._config.canvas_width,
                self._config.canvas_height,
            )

        if missing_homography:
            canvas = self._fuse_layout(canvas, missing_homography)
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


def _parse_exposure_gains(raw: Any) -> dict[int, float]:
    if not isinstance(raw, dict):
        return {}
    gains: dict[int, float] = {}
    for camera_id, value in raw.items():
        try:
            gains[int(camera_id)] = float(np.clip(float(value), 0.5, 1.8))
        except Exception:
            continue
    return gains


def _decode_blend_weights(
    raw_weights: Any,
    raw_shape: Any,
    canvas_width: int,
    canvas_height: int,
) -> dict[int, np.ndarray]:
    if not isinstance(raw_weights, dict) or not isinstance(raw_shape, (list, tuple)) or len(raw_shape) != 2:
        return {}
    try:
        height = int(raw_shape[0])
        width = int(raw_shape[1])
    except Exception:
        return {}
    if height <= 0 or width <= 0:
        return {}

    weights: dict[int, np.ndarray] = {}
    for camera_id, encoded in raw_weights.items():
        if not isinstance(encoded, str):
            continue
        try:
            payload = zlib.decompress(base64.b64decode(encoded.encode('ascii')))
            arr = np.frombuffer(payload, dtype=np.uint8).reshape((height, width)).astype(np.float32) / 255.0
            if width != canvas_width or height != canvas_height:
                arr = cv2.resize(arr, (canvas_width, canvas_height), interpolation=cv2.INTER_LINEAR)
            weights[int(camera_id)] = arr.astype(np.float32)
        except Exception:
            continue
    return weights


def _apply_exposure_gain(frame: np.ndarray, gain: float) -> np.ndarray:
    if abs(gain - 1.0) < 1e-3:
        return frame
    adjusted = frame.astype(np.float32) * float(gain)
    return np.clip(adjusted, 0, 255).astype(np.uint8)


def _weight_from_mask(mask: np.ndarray) -> np.ndarray:
    dist = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 5)
    max_value = float(dist.max())
    if max_value <= 0:
        return mask.astype(np.float32)
    return (dist / max_value).astype(np.float32)


def _feather_blend(
    warped_items: list[tuple[int, np.ndarray, np.ndarray]],
    stored_weights: dict[int, np.ndarray],
    canvas_width: int,
    canvas_height: int,
) -> np.ndarray:
    accum = np.zeros((canvas_height, canvas_width, 3), dtype=np.float32)
    weight_sum = np.zeros((canvas_height, canvas_width), dtype=np.float32)

    for camera_id, warped, mask in warped_items:
        weight = stored_weights.get(camera_id)
        if weight is None:
            weight = _weight_from_mask(mask)
        else:
            weight = cv2.resize(weight, (canvas_width, canvas_height), interpolation=cv2.INTER_LINEAR)
            weight = weight.astype(np.float32) * mask.astype(np.float32)
        accum += warped.astype(np.float32) * weight[..., None]
        weight_sum += weight

    valid = weight_sum > 1e-6
    output = np.zeros((canvas_height, canvas_width, 3), dtype=np.uint8)
    output[valid] = np.clip(accum[valid] / weight_sum[valid, None], 0, 255).astype(np.uint8)
    return output


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


def build_fusion_config_from_group(group: Any) -> FusionConfig:
    return FusionConfig(
        fusion_mode=str(group.fusion_mode or 'layout'),
        canvas_width=int(group.canvas_width or 1920),
        canvas_height=int(group.canvas_height or 1080),
        stitch_metadata=getattr(group, 'stitch_metadata', None),
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
                homography=member.homography,
                enabled=bool(member.enabled),
            )
            for member in group.members
        ],
    )
