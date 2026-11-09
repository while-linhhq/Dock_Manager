from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class ClahePreprocessConfig:
    clip_limit: float = 3.0
    tile_grid_size: int = 8
    enable_gray_world: bool = True
    enable_adaptive_threshold: bool = False
    threshold_blend: float = 0.15
    fast: bool = True


def preprocess_frame_clahe(
    frame_bgr: np.ndarray,
    config: ClahePreprocessConfig | None = None,
    *,
    fast: bool | None = None,
) -> np.ndarray:
    """
    Normalize uneven lighting per camera while preserving BGR output for YOLO/OCR.

    CLAHE is applied to the luminance channel only, so color cues remain usable for
    Re-ID. Optional threshold blending is intentionally conservative.

    ``fast``: ``None`` theo ``config.fast``; ``False`` chạy đúng bản cân bằng sáng
    float32 cũ (đường lùi khi cần so sánh bitwise).
    """
    if frame_bgr is None or frame_bgr.size == 0:
        return frame_bgr

    cfg = config or ClahePreprocessConfig()
    use_fast = cfg.fast if fast is None else bool(fast)
    if not cfg.enable_gray_world:
        normalized = frame_bgr
    elif use_fast:
        normalized = _gray_world_balance_fast(frame_bgr)
    else:
        normalized = _gray_world_balance(frame_bgr)

    lab = cv2.cvtColor(normalized, cv2.COLOR_BGR2LAB)
    lightness, channel_a, channel_b = cv2.split(lab)
    tile_size = max(2, int(cfg.tile_grid_size))
    clahe = cv2.createCLAHE(
        clipLimit=max(0.1, float(cfg.clip_limit)),
        tileGridSize=(tile_size, tile_size),
    )
    enhanced_l = clahe.apply(lightness)

    if cfg.enable_adaptive_threshold:
        enhanced_l = _blend_adaptive_threshold(
            enhanced_l,
            blend_ratio=float(cfg.threshold_blend),
        )

    enhanced_lab = cv2.merge((enhanced_l, channel_a, channel_b))
    return cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)


def _gray_world_balance(frame_bgr: np.ndarray) -> np.ndarray:
    """Bản tham chiếu (float32) — giữ nguyên để so sánh bitwise và làm đường lùi."""
    frame = frame_bgr.astype(np.float32)
    means = frame.reshape(-1, 3).mean(axis=0)
    global_mean = float(means.mean())
    if global_mean <= 1e-6:
        return frame_bgr

    scale = global_mean / np.maximum(means, 1.0)
    balanced = frame * scale.reshape(1, 1, 3)
    return np.clip(balanced, 0, 255).astype(np.uint8)


def _gray_world_balance_fast(frame_bgr: np.ndarray) -> np.ndarray:
    """Cân bằng sáng trên uint8: nhanh ~10× bản float32, lệch trung bình ~1.3 mức."""
    means = cv2.mean(frame_bgr)[:3]
    global_mean = float(sum(means) / 3.0)
    if global_mean <= 1e-6:
        return frame_bgr

    channels = [
        cv2.convertScaleAbs(
            np.ascontiguousarray(frame_bgr[:, :, index]),
            alpha=global_mean / max(mean, 1.0),
        )
        for index, mean in enumerate(means)
    ]
    return cv2.merge(channels)


def _blend_adaptive_threshold(lightness: np.ndarray, blend_ratio: float) -> np.ndarray:
    ratio = float(np.clip(blend_ratio, 0.0, 0.5))
    if ratio <= 0:
        return lightness

    thresholded = cv2.adaptiveThreshold(
        lightness,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        3,
    )
    blended = cv2.addWeighted(lightness, 1.0 - ratio, thresholded, ratio, 0)
    return blended.astype(np.uint8)
