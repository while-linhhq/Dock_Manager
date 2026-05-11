from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import cv2
import numpy as np

from app.services.ai.boat_tracker import TrackedBoat
from app.utils.ai.pipeline_utils import clamp_box

MOTION_STATIC = 'STATIC'
MOTION_MANEUVERING = 'MANEUVERING'
MOTION_TRANSITING = 'TRANSITING'


@dataclass
class _TrackMotionState:
    centroids: deque[tuple[float, float]] = field(default_factory=lambda: deque(maxlen=10))
    foreground_ratios: deque[float] = field(default_factory=lambda: deque(maxlen=10))


class MotionClassifier:
    def __init__(
        self,
        *,
        static_velocity_px_sec: float = 8.0,
        transit_velocity_px_sec: float = 35.0,
        foreground_ratio_threshold: float = 0.03,
    ) -> None:
        self._subtractor = cv2.createBackgroundSubtractorMOG2(
            history=300,
            varThreshold=32,
            detectShadows=True,
        )
        self._states: dict[str, _TrackMotionState] = {}
        self._static_velocity = float(static_velocity_px_sec)
        self._transit_velocity = float(transit_velocity_px_sec)
        self._foreground_threshold = float(foreground_ratio_threshold)

    def classify(self, frame_bgr: np.ndarray, track: TrackedBoat) -> str:
        foreground = self._subtractor.apply(frame_bgr)
        height, width = frame_bgr.shape[:2]
        x1, y1, x2, y2 = clamp_box(track.box, width, height)
        crop_mask = foreground[y1:y2, x1:x2]
        foreground_ratio = 0.0
        if crop_mask.size:
            foreground_ratio = float(np.count_nonzero(crop_mask > 0) / crop_mask.size)

        state = self._states.setdefault(str(track.track_id), _TrackMotionState())
        centroid = _centroid(track.box)
        state.centroids.append(centroid)
        state.foreground_ratios.append(foreground_ratio)

        speed = _speed_from_track(track)
        if speed <= 0 and len(state.centroids) >= 2:
            speed = _centroid_speed(state.centroids)
        avg_foreground = float(np.mean(state.foreground_ratios)) if state.foreground_ratios else 0.0

        if speed < self._static_velocity and avg_foreground < self._foreground_threshold:
            return MOTION_STATIC
        if speed >= self._transit_velocity:
            return MOTION_TRANSITING
        return MOTION_MANEUVERING

    def forget_missing(self, active_track_ids: set[str]) -> None:
        active = {str(track_id) for track_id in active_track_ids}
        for track_id in list(self._states.keys()):
            if track_id not in active:
                self._states.pop(track_id, None)


def _centroid(box: np.ndarray) -> tuple[float, float]:
    x1, y1, x2, y2 = box.astype(float)
    return ((x1 + x2) * 0.5, (y1 + y2) * 0.5)


def _speed_from_track(track: TrackedBoat) -> float:
    if track.velocity is None:
        return 0.0
    vx, vy = track.velocity
    return float(np.hypot(vx, vy))


def _centroid_speed(centroids: deque[tuple[float, float]]) -> float:
    if len(centroids) < 2:
        return 0.0
    first = centroids[0]
    last = centroids[-1]
    return float(np.hypot(last[0] - first[0], last[1] - first[1]) / max(1, len(centroids) - 1))
