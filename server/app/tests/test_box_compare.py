"""Test hàm so khớp box dùng chung cho harness A/B detection."""
from __future__ import annotations

import numpy as np

from app.utils.ai.box_compare import iou_matrix, match_boxes, summarize


def test_iou_matrix_known_values() -> None:
    box = np.array([0.0, 0.0, 10.0, 10.0], dtype=np.float32)
    boxes = np.array(
        [
            [0.0, 0.0, 10.0, 10.0],  # trùng khít → 1.0
            [5.0, 0.0, 15.0, 10.0],  # chồng 50% → 1/3
            [50.0, 50.0, 60.0, 60.0],  # rời → 0.0
        ],
        dtype=np.float32,
    )

    result = iou_matrix(box, boxes)

    assert result.shape == (3,)
    assert result[0] == 1.0
    assert abs(result[1] - 1.0 / 3.0) < 1e-6
    assert result[2] == 0.0


def test_identical_boxes_match_fully() -> None:
    a = np.array([[0.0, 0.0, 10.0, 10.0]], dtype=np.float32)
    b = np.array([[0.0, 0.0, 10.0, 10.0]], dtype=np.float32)

    ious, conf_deltas, only_a, only_b = match_boxes(a, [0.9], b, [0.9])

    assert ious == [1.0]
    assert conf_deltas == [0.0]
    assert (only_a, only_b) == (0, 0)


def test_disjoint_boxes_do_not_match() -> None:
    a = np.array([[0.0, 0.0, 10.0, 10.0]], dtype=np.float32)
    b = np.array([[50.0, 50.0, 60.0, 60.0]], dtype=np.float32)

    ious, conf_deltas, only_a, only_b = match_boxes(a, [0.9], b, [0.8])

    assert ious == []
    assert conf_deltas == []
    assert (only_a, only_b) == (1, 1)


def test_each_box_is_used_at_most_once() -> None:
    a = np.array([[0.0, 0.0, 10.0, 10.0], [1.0, 1.0, 11.0, 11.0]], dtype=np.float32)
    b = np.array([[0.0, 0.0, 10.0, 10.0]], dtype=np.float32)

    ious, _conf, only_a, only_b = match_boxes(a, [0.9, 0.8], b, [0.9])

    assert len(ious) == 1
    assert (only_a, only_b) == (1, 0)


def test_summarize_passes_when_within_gates() -> None:
    result = summarize(
        2,
        2,
        [0.995, 0.99],
        [0.004, 0.01],
        0,
        0,
        iou_gate=0.98,
        conf_gate=0.03,
    )

    assert result["passed"] is True
    assert result["reasons"] == []
    assert result["iou_min"] == 0.99
    assert result["conf_max"] == 0.01


def test_summarize_reports_iou_and_conf_reasons() -> None:
    result = summarize(
        1,
        1,
        [0.9],
        [0.2],
        0,
        0,
        iou_gate=0.98,
        conf_gate=0.03,
    )

    assert result["passed"] is False
    assert "iou" in result["reasons"]
    assert "conf" in result["reasons"]


def test_summarize_reports_unmatched_boxes() -> None:
    result = summarize(
        2,
        1,
        [1.0],
        [0.0],
        1,
        0,
        iou_gate=0.98,
        conf_gate=0.03,
    )

    assert result["passed"] is False
    assert "unmatched" in result["reasons"]


def test_match_boxes_handles_empty_inputs() -> None:
    empty = np.zeros((0, 4), dtype=np.float32)

    ious, conf_deltas, only_a, only_b = match_boxes(empty, [], empty, [])

    assert ious == []
    assert conf_deltas == []
    assert (only_a, only_b) == (0, 0)


def test_summarize_empty_scene_is_not_a_pass() -> None:
    """Bến trống (0 box cả hai đường) không chứng minh được gì → không được ĐẠT."""
    result = summarize(0, 0, [], [], 0, 0, iou_gate=0.98, conf_gate=0.03)

    assert result['passed'] is False
    assert 'empty_scene' in result['reasons']


def test_summarize_all_matched_passes() -> None:
    result = summarize(2, 2, [0.99, 0.995], [0.001, 0.002], 0, 0, iou_gate=0.98, conf_gate=0.03)

    assert result['passed'] is True
    assert result['reasons'] == []
