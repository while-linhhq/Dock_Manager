"""Test hình học letterbox: phải khớp đúng cách ultralytics letterbox ảnh trước khi suy luận."""
from __future__ import annotations

import numpy as np
import pytest

from app.utils.ai.letterbox import letterbox_frame, unletterbox_boxes


def _frame(height: int, width: int) -> np.ndarray:
    return np.full((height, width, 3), 7, dtype=np.uint8)


def test_letterbox_2560x1440_to_960_uses_scale_0375() -> None:
    result = letterbox_frame(_frame(1440, 2560), 960)

    assert result.content.shape == (540, 960, 3)
    assert result.scale == pytest.approx(0.375)
    assert (result.pad_x, result.pad_y) == (0, 210)
    assert result.size == 960


def test_letterbox_odd_size_center_pads() -> None:
    result = letterbox_frame(_frame(801, 1201), 960)

    assert result.content.shape[1] == 960
    assert result.pad_x == 0
    assert result.pad_y == (960 - result.content.shape[0]) // 2
    # phần pad còn lại nằm dưới (không làm tròn lệch 2 phía)
    assert result.pad_y * 2 <= 960 - result.content.shape[0]


def test_letterbox_upscales_small_frame_like_ultralytics() -> None:
    result = letterbox_frame(_frame(240, 320), 960)

    assert result.scale == pytest.approx(3.0)
    assert result.content.shape == (720, 960, 3)
    assert result.pad_x == 0
    assert result.pad_y == 120  # thiếu chiều cao nên pad trên/dưới


def test_padded_canvas_is_square_with_gray_border() -> None:
    result = letterbox_frame(_frame(1440, 2560), 960)

    canvas = result.padded(np.zeros_like(result.content))

    assert canvas.shape == (960, 960, 3)
    assert canvas.dtype == np.uint8
    assert (canvas[0] == 114).all()  # viền trên
    assert (canvas[-1] == 114).all()  # viền dưới
    assert (canvas[210] == 0).all()  # dòng đầu của nội dung


def test_unletterbox_round_trip_returns_full_res_boxes() -> None:
    result = letterbox_frame(_frame(1440, 2560), 960)
    full_res = np.array([[100.0, 200.0, 300.0, 400.0]], dtype=np.float32)
    in_letterbox = full_res * result.scale + np.array(
        [result.pad_x, result.pad_y, result.pad_x, result.pad_y], dtype=np.float32
    )

    restored = unletterbox_boxes(in_letterbox, result.scale, result.pad_x, result.pad_y)

    assert np.allclose(restored, full_res, atol=1e-3)


def test_unletterbox_empty_returns_empty_array() -> None:
    restored = unletterbox_boxes([], 0.375, 0, 210)

    assert restored.shape == (0, 4)
    assert restored.dtype == np.float32


def test_unletterbox_matches_ultralytics_scale_boxes() -> None:
    ops = pytest.importorskip('ultralytics.utils.ops')
    result = letterbox_frame(_frame(1440, 2560), 960)
    boxes = np.array([[100.0, 300.0, 400.0, 700.0], [10.0, 20.0, 30.0, 40.0]], dtype=np.float32)

    ours = unletterbox_boxes(
        boxes, result.scale, result.pad_x, result.pad_y, width=2560, height=1440
    )
    theirs = np.asarray(ops.scale_boxes((960, 960), boxes.copy(), (1440, 2560)))

    assert np.allclose(ours, theirs, atol=1e-3)


def test_unletterbox_clamps_box_in_pad_region() -> None:
    """Box nằm trong vùng pad (ngoài ảnh gốc) bị kẹp về biên, giống ultralytics."""
    result = letterbox_frame(_frame(1440, 2560), 960)
    in_pad = np.array([[100.0, 20.0, 400.0, 40.0]], dtype=np.float32)  # y < pad_y = 210

    clamped = unletterbox_boxes(
        in_pad, result.scale, result.pad_x, result.pad_y, width=2560, height=1440
    )
    unclamped = unletterbox_boxes(in_pad, result.scale, result.pad_x, result.pad_y)

    assert (clamped[:, [1, 3]] == 0).all()
    assert (unclamped[:, [1, 3]] < 0).all()


def test_unletterbox_map_back_matches_probe_geometry() -> None:
    """Box ở hệ 960×960 → full-res: đúng công thức (x-pad_x)/scale, (y-pad_y)/scale."""
    restored = unletterbox_boxes(
        np.array([[360.0, 420.0, 480.0, 570.0]], dtype=np.float32), 0.375, 0, 210
    )

    assert np.allclose(restored, [[960.0, 560.0, 1280.0, 960.0]], atol=1e-3)


def test_letterbox_rejects_zero_size_image() -> None:
    with pytest.raises(ValueError):
        letterbox_frame(_frame(0, 0), 960)
