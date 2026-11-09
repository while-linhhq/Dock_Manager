"""Quy đổi box giữa hệ toạ độ detect (tỉ lệ) và hệ full-res, và nới crop có kẹp biên."""
from __future__ import annotations

import numpy as np

from app.utils.ai.box_scale import pad_box, scale_boxes


def test_scale_boxes_roundtrip() -> None:
    boxes = np.array([[100.0, 50.0, 300.0, 150.0]], dtype=np.float32)

    back = scale_boxes(scale_boxes(boxes, 0.5), 2.0)

    assert np.allclose(back, boxes, atol=1e-6)
    assert back.dtype == np.float32


def test_scale_boxes_empty() -> None:
    empty = np.zeros((0, 4), dtype=np.float32)

    result = scale_boxes(empty, 0.5)

    assert result.shape == (0, 4)
    assert result.dtype == np.float32


def test_pad_box_is_clamped_to_frame() -> None:
    assert pad_box((0.0, 0.0, 10.0, 10.0), 0.5, 100, 100) == (0, 0, 15, 15)
    assert pad_box((90.0, 90.0, 100.0, 100.0), 0.5, 100, 100) == (85, 85, 100, 100)


def test_pad_box_zero_ratio_is_identity() -> None:
    assert pad_box((10.0, 20.0, 30.0, 40.0), 0.0, 200, 200) == (10, 20, 30, 40)


def test_pad_box_never_inverts_box() -> None:
    x1, y1, x2, y2 = pad_box((40.0, 40.0, 42.0, 42.0), 0.05, 100, 100)

    assert x1 <= x2 and y1 <= y2
