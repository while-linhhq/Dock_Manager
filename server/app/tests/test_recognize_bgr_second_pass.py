"""Regression: recognize_bgr runs the CLAHE second pass only when the raw
first pass is empty or below the confidence threshold. Skipping it on clear
crops roughly halves OCR CPU cost.
"""
from __future__ import annotations

from unittest.mock import patch

import numpy as np

from app.utils.ai.ship_id_recognizer import ShipIdRecognizer


def _make_recognizer(threshold: float = 0.85) -> ShipIdRecognizer:
    """Build without __init__ (paddle import is heavy / GPU-bound)."""
    rec = ShipIdRecognizer.__new__(ShipIdRecognizer)
    rec.ocr = object()
    rec._rule_engine = None
    rec.pattern = r"([A-Z50]{2})[-\s]?(\d{4})"
    rec._second_pass_conf_threshold = threshold
    return rec


def _img() -> np.ndarray:
    return np.zeros((64, 128, 3), dtype=np.uint8)


def test_skips_second_pass_when_first_pass_confident():
    rec = _make_recognizer(threshold=0.85)
    # First pass returns a high-confidence line: [[box], (text, conf)]
    lines = [[None, ("SG-1234", 0.97)]]
    with patch(
        "app.utils.ai.ship_id_recognizer.run_ocr_lines", return_value=lines
    ) as mock_run:
        result = rec.recognize_bgr(_img())

    assert mock_run.call_count == 1  # second (CLAHE) pass skipped
    assert result and result[0]["id"] == "SG-1234"


def test_runs_second_pass_when_first_pass_low_confidence():
    rec = _make_recognizer(threshold=0.85)
    lines = [[None, ("SG-1234", 0.40)]]  # below threshold
    with patch(
        "app.utils.ai.ship_id_recognizer.run_ocr_lines", return_value=lines
    ) as mock_run:
        rec.recognize_bgr(_img())

    assert mock_run.call_count == 2  # CLAHE second pass ran


def test_runs_second_pass_when_first_pass_empty():
    rec = _make_recognizer(threshold=0.85)
    with patch(
        "app.utils.ai.ship_id_recognizer.run_ocr_lines", return_value=[]
    ) as mock_run:
        rec.recognize_bgr(_img())

    assert mock_run.call_count == 2


def test_threshold_zero_always_runs_both_passes():
    rec = _make_recognizer(threshold=0.0)
    lines = [[None, ("SG-1234", 0.99)]]
    with patch(
        "app.utils.ai.ship_id_recognizer.run_ocr_lines", return_value=lines
    ) as mock_run:
        rec.recognize_bgr(_img())

    assert mock_run.call_count == 2  # threshold disabled → both passes
