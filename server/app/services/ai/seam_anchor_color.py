"""Dominant-color helpers for seam-anchor re-validation."""
from __future__ import annotations

import cv2
import numpy as np


def extract_dominant_hsv(
    frame_bgr: np.ndarray,
    bbox: tuple[int, int, int, int],
) -> tuple[int, int, int] | None:
    if frame_bgr is None or frame_bgr.size == 0:
        return None
    height, width = frame_bgr.shape[:2]
    x, y, w, h = bbox
    x = max(0, min(int(x), width - 1))
    y = max(0, min(int(y), height - 1))
    w = max(1, min(int(w), width - x))
    h = max(1, min(int(h), height - y))
    crop = frame_bgr[y : y + h, x : x + w]
    if crop.size == 0:
        return None
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    flat = hsv.reshape(-1, 3)
    median = np.median(flat, axis=0)
    return int(median[0]), int(median[1]), int(median[2])


def hsv_matches(
    baseline: tuple[int, int, int],
    sample: tuple[int, int, int],
    *,
    tolerance_h: int,
) -> bool:
    bh, bs, bv = baseline
    sh, ss, sv = sample
    dh = abs(int(bh) - int(sh))
    dh = min(dh, 180 - dh)
    if dh > int(tolerance_h):
        return False
    if abs(int(bs) - int(ss)) > 80:
        return False
    if abs(int(bv) - int(sv)) > 80:
        return False
    return True
