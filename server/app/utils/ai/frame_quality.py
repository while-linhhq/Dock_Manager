"""Heuristics to reject corrupt / placeholder RTSP frames before persisting."""

from __future__ import annotations

import cv2
import numpy as np


def is_usable_bgr_frame(
    frame: np.ndarray | None,
    *,
    min_std: float = 12.0,
    min_laplacian_var: float = 25.0,
    min_height: int = 64,
    min_width: int = 64,
) -> bool:
    if frame is None or frame.size == 0:
        return False
    if frame.ndim != 3 or frame.shape[2] < 3:
        return False
    height, width = frame.shape[:2]
    if height < min_height or width < min_width:
        return False

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    std = float(gray.std())
    if std < min_std:
        return False

    lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    if lap_var < min_laplacian_var:
        return False

    # Reject near-flat gray slabs (common H.264 decode glitch).
    if 100.0 <= float(gray.mean()) <= 156.0 and std < 18.0:
        return False

    return True
