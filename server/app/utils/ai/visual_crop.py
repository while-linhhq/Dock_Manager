from __future__ import annotations

import numpy as np


def inset_box(
    box: tuple[float, float, float, float] | np.ndarray,
    *,
    frame_w: int,
    frame_h: int,
    inset_ratio: float = 0.06,
) -> tuple[int, int, int, int]:
    """Shrink bbox inward to reduce background in visual embedding crops."""
    x1, y1, x2, y2 = (float(box[0]), float(box[1]), float(box[2]), float(box[3]))
    width = max(1.0, x2 - x1)
    height = max(1.0, y2 - y1)
    dx = width * max(0.0, min(0.25, inset_ratio))
    dy = height * max(0.0, min(0.25, inset_ratio))
    nx1 = max(0, int(round(x1 + dx)))
    ny1 = max(0, int(round(y1 + dy)))
    nx2 = min(frame_w, int(round(x2 - dx)))
    ny2 = min(frame_h, int(round(y2 - dy)))
    if nx2 <= nx1 or ny2 <= ny1:
        return int(x1), int(y1), int(x2), int(y2)
    return nx1, ny1, nx2, ny2


def crop_frame_box(
    frame: np.ndarray,
    box: tuple[float, float, float, float] | np.ndarray,
    *,
    inset_ratio: float = 0.06,
) -> np.ndarray | None:
    if frame is None or frame.size == 0:
        return None
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = inset_box(box, frame_w=w, frame_h=h, inset_ratio=inset_ratio)
    if x2 <= x1 or y2 <= y1:
        return None
    crop = frame[y1:y2, x1:x2]
    return crop if crop.size > 0 else None
