"""PaddleOCR 3.x adapter — normalize predict() output to legacy line tuples."""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def _configure_paddle_runtime_env() -> None:
    import os

    os.environ.setdefault('PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK', 'True')
    os.environ.setdefault('FLAGS_enable_pir_api', '0')
    os.environ.setdefault('FLAGS_use_mkldnn', '0')


def _settings_defaults() -> dict[str, Any]:
    """Đọc cấu hình model/TRT từ settings; thiếu settings thì trả rỗng (giữ hành vi cũ)."""
    try:
        from app.core.config import settings
    except Exception:
        return {}

    return {
        'use_tensorrt': bool(getattr(settings, 'PADDLE_USE_TENSORRT', False)),
        'precision': str(getattr(settings, 'PADDLE_TRT_PRECISION', 'fp16') or 'fp16'),
        'det_model_dir': str(getattr(settings, 'PADDLE_OCR_DET_MODEL_DIR', '') or '').strip(),
        'rec_model_dir': str(getattr(settings, 'PADDLE_OCR_REC_MODEL_DIR', '') or '').strip(),
    }


def create_paddle_ocr(
    *,
    lang: str = 'en',
    use_gpu: bool = False,
    show_log: bool = False,
    use_tensorrt: bool | None = None,
    precision: str | None = None,
    det_model_dir: str | None = None,
    rec_model_dir: str | None = None,
):
    """Dựng PaddleOCR.

    Model lấy từ ``models/paddle_ocr/`` nếu thư mục tồn tại (khỏi tải về ~/.paddlex).
    Bật TensorRT fp16 khi có cấu hình — Paddle tự build + cache engine con
    (``run_mode=trt_fp16``); thiếu TensorRT hoặc lỗi build thì tự lùi về chế độ
    thường thay vì làm chết pipeline.
    """
    _configure_paddle_runtime_env()
    from paddleocr import PaddleOCR

    defaults = _settings_defaults()
    if use_tensorrt is None:
        use_tensorrt = bool(defaults.get('use_tensorrt', False))
    if precision is None:
        precision = str(defaults.get('precision', 'fp16'))
    det_model_dir = det_model_dir or defaults.get('det_model_dir') or ''
    rec_model_dir = rec_model_dir or defaults.get('rec_model_dir') or ''

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
    if det_model_dir and os.path.isdir(det_model_dir):
        kwargs['text_detection_model_dir'] = det_model_dir
    if rec_model_dir and os.path.isdir(rec_model_dir):
        kwargs['text_recognition_model_dir'] = rec_model_dir

    if use_tensorrt and use_gpu:
        try:
            ocr = PaddleOCR(**kwargs, use_tensorrt=True, precision=precision)
            logger.info('PaddleOCR dùng TensorRT (%s)', precision)
            return ocr
        except Exception as exc:  # noqa: BLE001 - lùi về chế độ thường
            logger.warning(
                'PaddleOCR TensorRT (%s) không dùng được, lùi về chế độ thường: %s',
                precision,
                exc,
            )
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
