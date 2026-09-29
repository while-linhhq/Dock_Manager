"""Test CLAHE: đường nhanh uint8 phải xấp xỉ đường tham chiếu float32 và lùi được.

Ngưỡng sai lệch lấy từ số đo thật trên frame camera 2560×1440 và ảnh tổng hợp:
lệch trung bình 1.24-1.33 mức uint8, max 8-16, ~98-99 % pixel lệch ≤ 4.
"""
from __future__ import annotations

import cv2
import numpy as np

from app.services.ai.clahe_preprocessor import ClahePreprocessConfig, preprocess_frame_clahe


def _frame_with_color_cast() -> np.ndarray:
    rng = np.random.default_rng(7)
    frame = np.clip(rng.normal(120, 40, (240, 320, 3)), 0, 255).astype(np.uint8)
    frame = cv2.GaussianBlur(frame, (5, 5), 0)
    frame[:, :, 0] = (frame[:, :, 0] * 0.6).astype(np.uint8)  # ám xanh có chủ ý
    return frame


def test_config_default_is_fast() -> None:
    assert ClahePreprocessConfig().fast is True


def test_default_follows_config_fast_flag() -> None:
    frame = _frame_with_color_cast()
    slow = ClahePreprocessConfig(clip_limit=3.0, tile_grid_size=8, fast=False)
    quick = ClahePreprocessConfig(clip_limit=3.0, tile_grid_size=8, fast=True)

    assert np.array_equal(
        preprocess_frame_clahe(frame, slow),
        preprocess_frame_clahe(frame, slow, fast=False),
    )
    assert np.array_equal(
        preprocess_frame_clahe(frame, quick),
        preprocess_frame_clahe(frame, quick, fast=True),
    )


def test_gray_world_disabled_is_bitwise_identical() -> None:
    frame = _frame_with_color_cast()
    config = ClahePreprocessConfig(clip_limit=3.0, tile_grid_size=8, enable_gray_world=False)

    assert np.array_equal(
        preprocess_frame_clahe(frame, config, fast=True),
        preprocess_frame_clahe(frame, config, fast=False),
    )


def test_fast_close_to_reference_with_gray_world() -> None:
    frame = _frame_with_color_cast()
    config = ClahePreprocessConfig(clip_limit=3.0, tile_grid_size=8, enable_gray_world=True)

    reference = preprocess_frame_clahe(frame, config, fast=False).astype(np.int16)
    fast = preprocess_frame_clahe(frame, config, fast=True).astype(np.int16)
    delta = np.abs(reference - fast)

    assert delta.mean() <= 2.0
    assert delta.max() <= 24
    assert (delta <= 4).mean() >= 0.95


def test_fast_keeps_gray_world_balancing() -> None:
    """Đường nhanh phải gần bản tham chiếu hơn hẳn bản bỏ cân bằng sáng."""
    frame = _frame_with_color_cast()
    with_gray_world = ClahePreprocessConfig(clip_limit=3.0, tile_grid_size=8, enable_gray_world=True)
    without_gray_world = ClahePreprocessConfig(clip_limit=3.0, tile_grid_size=8, enable_gray_world=False)

    reference = preprocess_frame_clahe(frame, with_gray_world, fast=False).astype(np.int16)
    fast = preprocess_frame_clahe(frame, with_gray_world, fast=True).astype(np.int16)
    no_balance = preprocess_frame_clahe(frame, without_gray_world, fast=True).astype(np.int16)

    assert np.abs(reference - fast).mean() < np.abs(reference - no_balance).mean() / 2


def test_shape_dtype_preserved_for_non_contiguous_input() -> None:
    frame = _frame_with_color_cast()[:, ::-1]
    config = ClahePreprocessConfig(clip_limit=3.0, tile_grid_size=8, enable_gray_world=True)

    output = preprocess_frame_clahe(frame, config, fast=True)

    assert output.shape == frame.shape
    assert output.dtype == np.uint8
    assert output.flags['C_CONTIGUOUS']
