"""PaddleOCR 3.x adapter — normalize predict() output to legacy line tuples."""
from __future__ import annotations

from typing import Any


def _configure_paddle_runtime_env() -> None:
    import os

    os.environ.setdefault('PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK', 'True')
    os.environ.setdefault('FLAGS_enable_pir_api', '0')
    os.environ.setdefault('FLAGS_use_mkldnn', '0')


def create_paddle_ocr(
    *,
    lang: str = 'en',
    use_gpu: bool = False,
    show_log: bool = False,
):
    _configure_paddle_runtime_env()
    from paddleocr import PaddleOCR

    device = 'gpu:0' if use_gpu else 'cpu'
    kwargs: dict[str, Any] = {
        'lang': lang,
        'device': device,
        'enable_mkldnn': False,
        'use_doc_orientation_classify': False,
        'use_doc_unwarping': False,
        'use_textline_orientation': False,
    }
    if show_log:
        kwargs['show_log'] = show_log
    return PaddleOCR(**kwargs)


def _coerce_sequence(value: Any) -> list[Any]:
    if value is None:
        return []
    if hasattr(value, 'tolist'):
        value = value.tolist()
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _pick_boxes(payload: dict[str, Any]) -> list[Any]:
    for key in ('rec_boxes', 'dt_polys', 'rec_polys'):
        seq = _coerce_sequence(payload.get(key))
        if seq:
            return seq
    return []


def _result_payload(res: Any) -> dict[str, Any]:
    if isinstance(res, dict):
        inner = res.get('res')
        if isinstance(inner, dict):
            return inner
        if 'rec_texts' in res:
            return res
        return res
    for attr in ('res', 'json'):
        if hasattr(res, attr):
            value = getattr(res, attr)
            if callable(value):
                try:
                    value = value()
                except TypeError:
                    continue
            if isinstance(value, dict):
                inner = value.get('res')
                return inner if isinstance(inner, dict) else value
    for attr in ('rec_texts', 'rec_scores'):
        if hasattr(res, attr):
            return {
                'rec_texts': getattr(res, 'rec_texts', None),
                'rec_scores': getattr(res, 'rec_scores', None),
                'rec_boxes': getattr(res, 'rec_boxes', None),
                'dt_polys': getattr(res, 'dt_polys', None),
                'rec_polys': getattr(res, 'rec_polys', None),
            }
    to_dict = getattr(res, 'to_dict', None)
    if callable(to_dict):
        data = to_dict()
        if isinstance(data, dict):
            inner = data.get('res')
            return inner if isinstance(inner, dict) else data
    return {}


def _normalize_scores(scores: Any, count: int) -> list[float]:
    if scores is None:
        return [0.0] * count
    if hasattr(scores, 'tolist'):
        scores = scores.tolist()
    if not isinstance(scores, (list, tuple)):
        return [float(scores)] * count
    return [float(s) for s in scores]


def run_ocr_lines(ocr: Any, img_bgr) -> list[list[Any]]:
    """
    Run PaddleOCR predict and return legacy-style lines:
    ``[[box_or_none], (text, confidence), ...]``.
    """
    predict = getattr(ocr, 'predict', None)
    if not callable(predict):
        legacy = getattr(ocr, 'ocr', None)
        if callable(legacy):
            raw = legacy(img_bgr, cls=True)
            if not raw:
                return []
            page = raw[0] if raw else []
            return list(page) if page else []
        return []

    pages = predict(img_bgr)
    if pages is None:
        return []
    if not isinstance(pages, (list, tuple)):
        pages = [pages]

    lines: list[list[Any]] = []
    for page in pages:
        payload = _result_payload(page)
        texts = _coerce_sequence(payload.get('rec_texts'))
        scores = _normalize_scores(payload.get('rec_scores'), len(texts))
        boxes = _pick_boxes(payload)
        for index, text in enumerate(texts):
            box = boxes[index] if index < len(boxes) else None
            conf = scores[index] if index < len(scores) else 0.0
            lines.append([box, (str(text), float(conf))])
    return lines
