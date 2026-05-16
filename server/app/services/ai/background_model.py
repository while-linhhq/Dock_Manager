"""
Per-camera background model for seam anchor verification.

Uses OpenCV MOG2 background subtractor with:
- Auto-seed phase: first N frames feed the model with high learning rate.
- Adaptive phase: learning rate drops once `is_ready()`.
- Manual lock: replace internal background with a user-captured "empty port" frame.
- Region freeze: stop learning on a specific ROI (so anchored boats don't get
  absorbed into the background after long mooring).
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Iterable

import cv2
import numpy as np


@dataclass(frozen=True)
class BackgroundModelConfig:
    history: int = 500
    var_threshold: float = 25.0
    min_seed_frames: int = 100
    morph_kernel_size: int = 5
    default_learning_rate: float = 0.0005
    lock_replay_count: int = 30


class BackgroundModel:
    """Wrap MOG2 with explicit seed-and-freeze controls."""

    def __init__(self, config: BackgroundModelConfig | None = None) -> None:
        self._config = config or BackgroundModelConfig()
        self._subtractor = cv2.createBackgroundSubtractorMOG2(
            history=self._config.history,
            varThreshold=self._config.var_threshold,
            detectShadows=False,
        )
        self._seed_count = 0
        self._frozen_regions: list[tuple[int, int, int, int]] = []
        self._kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (self._config.morph_kernel_size, self._config.morph_kernel_size),
        )
        self._lock = threading.Lock()

    @property
    def config(self) -> BackgroundModelConfig:
        return self._config

    def is_ready(self) -> bool:
        return self._seed_count >= self._config.min_seed_frames

    def update(self, frame_bgr: np.ndarray, learning_rate: float | None = None) -> np.ndarray:
        """Feed a frame and return raw foreground mask.

        - During seed phase, learning_rate is forced high (auto-learn baseline).
        - During adaptive phase, frozen regions are pasted from a static
          background image generated on-the-fly so MOG2 won't drift inside them.
        """
        if frame_bgr is None or frame_bgr.size == 0:
            return np.zeros((0, 0), dtype=np.uint8)

        with self._lock:
            if not self.is_ready():
                lr = 1.0 / max(1, self._config.min_seed_frames)
                mask = self._subtractor.apply(frame_bgr, learningRate=lr)
                self._seed_count += 1
                return mask

            effective_lr = (
                learning_rate
                if learning_rate is not None
                else self._config.default_learning_rate
            )

            if self._frozen_regions:
                masked_frame = self._mask_frozen_regions(frame_bgr)
                mask = self._subtractor.apply(masked_frame, learningRate=effective_lr)
                full_mask = self._subtractor.apply(frame_bgr, learningRate=0.0)
                return full_mask

            return self._subtractor.apply(frame_bgr, learningRate=effective_lr)

    def foreground_ratio(self, frame_bgr: np.ndarray, roi: tuple[int, int, int, int]) -> float:
        """Apply the model and return fg pixel ratio inside the ROI."""
        if frame_bgr is None or frame_bgr.size == 0:
            return 0.0
        with self._lock:
            mask = self._subtractor.apply(frame_bgr, learningRate=0.0)
        roi_mask = self._extract_roi(mask, roi, frame_bgr.shape)
        if roi_mask.size == 0:
            return 0.0
        clean = self._clean(roi_mask)
        return float(np.count_nonzero(clean > 0) / clean.size)

    def foreground_crop(
        self,
        frame_bgr: np.ndarray,
        roi: tuple[int, int, int, int],
    ) -> tuple[np.ndarray, np.ndarray]:
        """Return (crop_bgr, fg_mask_in_crop) for a ROI. Empty arrays on miss."""
        if frame_bgr is None or frame_bgr.size == 0:
            empty = np.zeros((0, 0), dtype=np.uint8)
            return empty, empty
        with self._lock:
            mask = self._subtractor.apply(frame_bgr, learningRate=0.0)
        x, y, w, h = self._clamp_roi(roi, frame_bgr.shape)
        if w <= 0 or h <= 0:
            empty = np.zeros((0, 0), dtype=np.uint8)
            return empty, empty
        crop = frame_bgr[y:y + h, x:x + w].copy()
        roi_mask = mask[y:y + h, x:x + w]
        cleaned = self._clean(roi_mask)
        return crop, cleaned

    def lock_from_frame(self, frame_bgr: np.ndarray) -> bool:
        """Replay one frame multiple times to overwrite background."""
        if frame_bgr is None or frame_bgr.size == 0:
            return False
        replay = max(1, int(self._config.lock_replay_count))
        with self._lock:
            for _ in range(replay):
                self._subtractor.apply(frame_bgr, learningRate=1.0)
            self._seed_count = max(self._seed_count, self._config.min_seed_frames)
        return True

    def freeze_regions(self, regions: Iterable[tuple[int, int, int, int]]) -> None:
        with self._lock:
            self._frozen_regions = [tuple(int(v) for v in roi) for roi in regions]  # type: ignore[misc]

    def clear_frozen_regions(self) -> None:
        with self._lock:
            self._frozen_regions = []

    def reset(self) -> None:
        with self._lock:
            self._subtractor = cv2.createBackgroundSubtractorMOG2(
                history=self._config.history,
                varThreshold=self._config.var_threshold,
                detectShadows=False,
            )
            self._seed_count = 0
            self._frozen_regions = []

    def _mask_frozen_regions(self, frame_bgr: np.ndarray) -> np.ndarray:
        masked = frame_bgr.copy()
        for roi in self._frozen_regions:
            x, y, w, h = self._clamp_roi(roi, frame_bgr.shape)
            if w > 0 and h > 0:
                masked[y:y + h, x:x + w] = 0
        return masked

    def _clean(self, mask: np.ndarray) -> np.ndarray:
        if mask.size == 0:
            return mask
        opened = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self._kernel)
        return cv2.morphologyEx(opened, cv2.MORPH_CLOSE, self._kernel)

    @staticmethod
    def _clamp_roi(
        roi: tuple[int, int, int, int],
        frame_shape: tuple[int, ...],
    ) -> tuple[int, int, int, int]:
        height, width = frame_shape[:2]
        x, y, w, h = (int(v) for v in roi)
        x = max(0, min(width, x))
        y = max(0, min(height, y))
        w = max(0, min(width - x, w))
        h = max(0, min(height - y, h))
        return x, y, w, h

    @classmethod
    def _extract_roi(
        cls,
        mask: np.ndarray,
        roi: tuple[int, int, int, int],
        frame_shape: tuple[int, ...],
    ) -> np.ndarray:
        x, y, w, h = cls._clamp_roi(roi, frame_shape)
        if w <= 0 or h <= 0:
            return np.zeros((0, 0), dtype=np.uint8)
        return mask[y:y + h, x:x + w]


class BackgroundModelRegistry:
    """Thread-safe per-camera registry of BackgroundModel instances."""

    def __init__(self, config: BackgroundModelConfig | None = None) -> None:
        self._config = config or BackgroundModelConfig()
        self._models: dict[int, BackgroundModel] = {}
        self._lock = threading.RLock()

    def ensure(self, camera_id: int) -> BackgroundModel:
        camera_key = int(camera_id)
        with self._lock:
            model = self._models.get(camera_key)
            if model is None:
                model = BackgroundModel(self._config)
                self._models[camera_key] = model
            return model

    def get(self, camera_id: int) -> BackgroundModel | None:
        with self._lock:
            return self._models.get(int(camera_id))

    def camera_ids(self) -> list[int]:
        with self._lock:
            return list(self._models.keys())

    def lock_from_frame(self, camera_id: int, frame_bgr: np.ndarray) -> bool:
        model = self.ensure(camera_id)
        return model.lock_from_frame(frame_bgr)

    def update(
        self,
        camera_id: int,
        frame_bgr: np.ndarray,
        learning_rate: float | None = None,
    ) -> None:
        model = self.ensure(camera_id)
        model.update(frame_bgr, learning_rate=learning_rate)
