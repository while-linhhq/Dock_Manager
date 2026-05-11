from __future__ import annotations

import threading
from dataclasses import dataclass

import cv2
import numpy as np

from app.utils.ai.pipeline_utils import clamp_box


@dataclass(frozen=True)
class StitchRequest:
    camera_id: int
    box: np.ndarray
    side: str


class LocalStitcher:
    """
    Stitch only the overlap band between adjacent cameras for OCR.

    Homographies are expected to map camera coordinates into a shared panorama
    canvas. For local OCR, the adjacent frame is warped back into the current
    camera's coordinate system and blended around the boundary.
    """

    def __init__(
        self,
        camera_order: list[int],
        homographies: dict[int, list[list[float]] | None],
        overlap_px: int = 320,
    ) -> None:
        self._camera_order = [int(camera_id) for camera_id in camera_order]
        self._camera_index = {
            camera_id: index for index, camera_id in enumerate(self._camera_order)
        }
        self._homographies = {
            int(camera_id): np.asarray(matrix, dtype=np.float32)
            for camera_id, matrix in homographies.items()
            if matrix is not None
        }
        self._overlap_px = max(32, int(overlap_px))
        self._frames: dict[int, np.ndarray] = {}
        self._lock = threading.RLock()

    def set_latest_frame(self, camera_id: int, frame_bgr: np.ndarray) -> None:
        if frame_bgr is None or frame_bgr.size == 0:
            return
        with self._lock:
            self._frames[int(camera_id)] = frame_bgr.copy()

    def adjacent_for_side(self, camera_id: int, side: str) -> int | None:
        index = self._camera_index.get(int(camera_id))
        if index is None:
            return None
        if side == 'left' and index > 0:
            return self._camera_order[index - 1]
        if side == 'right' and index + 1 < len(self._camera_order):
            return self._camera_order[index + 1]
        return None

    def stitch_for_track(
        self,
        camera_id: int,
        box: np.ndarray,
        side: str,
    ) -> np.ndarray | None:
        adjacent_id = self.adjacent_for_side(camera_id, side)
        if adjacent_id is None:
            return None

        with self._lock:
            frame = self._frames.get(int(camera_id))
            adjacent = self._frames.get(int(adjacent_id))
            if frame is None or adjacent is None:
                return None
            frame = frame.copy()
            adjacent = adjacent.copy()

        warped_adjacent = self._warp_adjacent_to_camera(
            int(camera_id),
            int(adjacent_id),
            frame.shape,
            adjacent,
        )
        if warped_adjacent is None:
            return self._fallback_edge_concat(frame, adjacent, box, side)

        blended = _blend_overlap(frame, warped_adjacent)
        return _crop_boundary_region(blended, box, side, self._overlap_px)

    def _warp_adjacent_to_camera(
        self,
        camera_id: int,
        adjacent_id: int,
        target_shape: tuple[int, ...],
        adjacent_frame: np.ndarray,
    ) -> np.ndarray | None:
        h_camera = self._homographies.get(camera_id)
        h_adjacent = self._homographies.get(adjacent_id)
        if h_camera is None or h_adjacent is None:
            return None
        try:
            transform = np.linalg.inv(h_camera) @ h_adjacent
            height, width = target_shape[:2]
            return cv2.warpPerspective(
                adjacent_frame,
                transform.astype(np.float32),
                (int(width), int(height)),
            )
        except Exception:
            return None

    def _fallback_edge_concat(
        self,
        frame: np.ndarray,
        adjacent: np.ndarray,
        box: np.ndarray,
        side: str,
    ) -> np.ndarray | None:
        frame_h, frame_w = frame.shape[:2]
        adjacent_h, adjacent_w = adjacent.shape[:2]
        x1, y1, x2, y2 = clamp_box(box, frame_w, frame_h)
        pad_y = max(20, (y2 - y1) // 2)
        y1 = max(0, y1 - pad_y)
        y2 = min(frame_h, y2 + pad_y)
        if y2 <= y1:
            return None

        overlap = min(self._overlap_px, frame_w, adjacent_w)
        if side == 'left':
            current_band = frame[y1:y2, 0:overlap]
            adjacent_band = adjacent[
                max(0, min(adjacent_h - 1, y1)):max(0, min(adjacent_h, y2)),
                max(0, adjacent_w - overlap):adjacent_w,
            ]
            return _resize_and_concat(adjacent_band, current_band)

        current_band = frame[y1:y2, max(0, frame_w - overlap):frame_w]
        adjacent_band = adjacent[
            max(0, min(adjacent_h - 1, y1)):max(0, min(adjacent_h, y2)),
            0:overlap,
        ]
        return _resize_and_concat(current_band, adjacent_band)


def _blend_overlap(frame: np.ndarray, warped_adjacent: np.ndarray) -> np.ndarray:
    mask = np.any(warped_adjacent > 0, axis=2).astype(np.uint8)
    if int(mask.sum()) == 0:
        return frame
    blurred_mask = cv2.GaussianBlur(mask.astype(np.float32), (31, 31), 0)
    max_value = float(blurred_mask.max())
    if max_value > 0:
        blurred_mask /= max_value
    alpha = blurred_mask[..., None]
    blended = frame.astype(np.float32) * (1.0 - alpha) + warped_adjacent.astype(np.float32) * alpha
    return np.clip(blended, 0, 255).astype(np.uint8)


def _crop_boundary_region(
    frame: np.ndarray,
    box: np.ndarray,
    side: str,
    overlap_px: int,
) -> np.ndarray | None:
    height, width = frame.shape[:2]
    x1, y1, x2, y2 = clamp_box(box, width, height)
    pad_y = max(20, (y2 - y1) // 2)
    y1 = max(0, y1 - pad_y)
    y2 = min(height, y2 + pad_y)
    if side == 'left':
        x1 = 0
        x2 = min(width, max(int(x2), overlap_px))
    else:
        x1 = max(0, min(int(x1), width - overlap_px))
        x2 = width
    if x2 <= x1 or y2 <= y1:
        return None
    return frame[y1:y2, x1:x2].copy()


def _resize_and_concat(left: np.ndarray, right: np.ndarray) -> np.ndarray | None:
    if left is None or right is None or left.size == 0 or right.size == 0:
        return None
    height = max(1, min(left.shape[0], right.shape[0]))
    left_resized = cv2.resize(left, (left.shape[1], height), interpolation=cv2.INTER_AREA)
    right_resized = cv2.resize(right, (right.shape[1], height), interpolation=cv2.INTER_AREA)
    return np.concatenate([left_resized, right_resized], axis=1)
