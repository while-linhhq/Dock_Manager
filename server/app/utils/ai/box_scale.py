"""Quy đổi box giữa hệ toạ độ detect (frame đã thu nhỏ) và hệ toạ độ full-res.

Toàn pipeline dùng toạ độ full-res làm chuẩn (tracker, ngưỡng lọc, crop OCR/embedding,
overlay, media). Khi bật `detect_scale < 1.0`, box của detector nằm ở hệ đã thu nhỏ và
phải quy về full-res ngay sau khi suy luận — chỉ một điểm quy đổi duy nhất.
"""
from __future__ import annotations

import numpy as np


def scale_boxes(boxes: np.ndarray, factor: float) -> np.ndarray:
    """Nhân toạ độ box (N, 4) với ``factor``, giữ nguyên dtype float32."""
    array = np.asarray(boxes, dtype=np.float32).reshape(-1, 4)
    if array.size == 0:
        return array.astype(np.float32, copy=False)
    return (array * float(factor)).astype(np.float32, copy=False)


def pad_box(
    box: tuple[float, float, float, float] | np.ndarray,
    ratio: float,
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    """Nới box thêm ``ratio`` lần kích thước mỗi cạnh, kẹp trong khung ảnh."""
    x1, y1, x2, y2 = (float(value) for value in box[:4])
    pad_x = (x2 - x1) * float(ratio)
    pad_y = (y2 - y1) * float(ratio)
    left = max(0, int(round(x1 - pad_x)))
    top = max(0, int(round(y1 - pad_y)))
    right = min(int(width), int(round(x2 + pad_x)))
    bottom = min(int(height), int(round(y2 + pad_y)))
    return left, top, max(left, right), max(top, bottom)
