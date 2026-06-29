import numpy as np

from app.utils.ai.paddle_ocr_adapter import _result_payload, run_ocr_lines


def test_result_payload_nested_res():
    payload = _result_payload({'res': {'rec_texts': ['AB-1234'], 'rec_scores': [0.9]}})
    assert payload['rec_texts'] == ['AB-1234']


def test_run_ocr_lines_handles_numpy_boxes():
    class _Page:
        rec_texts = ['BS-1234']
        rec_scores = np.array([0.91], dtype=np.float32)
        rec_boxes = np.array([[1, 2, 3, 4]], dtype=np.int32)

    class _Ocr:
        def predict(self, img):
            return [_Page()]

    lines = run_ocr_lines(_Ocr(), np.zeros((8, 8, 3), dtype=np.uint8))
    assert len(lines) == 1
    assert lines[0][1][0] == 'BS-1234'


def test_run_ocr_lines_legacy_fallback():
    class _LegacyOcr:
        def ocr(self, img, cls=True):
            return [
                [
                    [[[0, 0], [1, 0], [1, 1], [0, 1]], ('SG-1234', 0.88)],
                ],
            ]

    lines = run_ocr_lines(_LegacyOcr(), np.zeros((8, 8, 3), dtype=np.uint8))
    assert len(lines) == 1
    assert lines[0][1][0] == 'SG-1234'
