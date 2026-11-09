"""Hàm so khớp box dùng chung cho các script đối chiếu kết quả nhận diện.

Dùng cho `scripts/verify_engines.py` (.pt vs .engine) và `scripts/ab_detect.py`
(đường tiền xử lý hiện tại vs đường ứng viên). Chỉ hàm thuần, không phụ thuộc
model hay cấu hình.
"""
from __future__ import annotations

from collections.abc import Sequence

import numpy as np


def iou_matrix(box: np.ndarray, boxes: np.ndarray) -> np.ndarray:
    """IoU của một box (4 phần tử xyxy) với mảng box (N, 4) → mảng (N,)."""
    if len(boxes) == 0:
        return np.zeros(0, dtype=np.float32)
    box = np.asarray(box, dtype=np.float32)
    boxes = np.asarray(boxes, dtype=np.float32)
    x1 = np.maximum(box[0], boxes[:, 0])
    y1 = np.maximum(box[1], boxes[:, 1])
    x2 = np.minimum(box[2], boxes[:, 2])
    y2 = np.minimum(box[3], boxes[:, 3])
    inter = np.clip(x2 - x1, 0.0, None) * np.clip(y2 - y1, 0.0, None)
    area_a = (box[2] - box[0]) * (box[3] - box[1])
    area_b = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    union = area_a + area_b - inter
    return np.where(union > 0, inter / np.maximum(union, 1e-9), 0.0).astype(np.float32)


def match_boxes(
    a_boxes: np.ndarray,
    a_conf: Sequence[float],
    b_boxes: np.ndarray,
    b_conf: Sequence[float],
    iou_thr: float = 0.5,
) -> tuple[list[float], list[float], int, int]:
    """Ghép cặp box tham lam theo IoU cao nhất; mỗi box chỉ dùng một lần.

    Trả về ``(ious, conf_deltas, only_a, only_b)``: IoU của các cặp đã ghép, độ
    lệch conf tuyệt đối của từng cặp, số box chỉ có ở A, số box chỉ có ở B.
    """
    a_boxes = np.asarray(a_boxes, dtype=np.float32).reshape(-1, 4)
    b_boxes = np.asarray(b_boxes, dtype=np.float32).reshape(-1, 4)
    ious: list[float] = []
    conf_deltas: list[float] = []
    used: set[int] = set()
    for index, box in enumerate(a_boxes):
        candidates = iou_matrix(box, b_boxes)
        best_iou, best_index = 0.0, -1
        for j, value in enumerate(candidates):
            if j in used:
                continue
            if value > best_iou:
                best_iou, best_index = float(value), j
        if best_index >= 0 and best_iou >= iou_thr:
            used.add(best_index)
            ious.append(best_iou)
            conf_deltas.append(abs(float(a_conf[index]) - float(b_conf[best_index])))
    only_a = len(a_boxes) - len(ious)
    only_b = len(b_boxes) - len(used)
    return ious, conf_deltas, only_a, only_b


def summarize(
    n_a: int,
    n_b: int,
    ious: Sequence[float],
    conf_deltas: Sequence[float],
    only_a: int,
    only_b: int,
    *,
    iou_gate: float,
    conf_gate: float,
) -> dict:
    """Tổng hợp kết quả so khớp và kết luận ĐẠT/KHÔNG theo cổng cho trước."""
    iou_min = float(min(ious)) if ious else 0.0
    iou_mean = float(np.mean(ious)) if ious else 0.0
    conf_max = float(max(conf_deltas)) if conf_deltas else 0.0

    reasons: list[str] = []
    if not n_a and not n_b:
        # Bến trống: hai đường cùng không thấy gì thì A/B không chứng minh được gì.
        reasons.append('empty_scene')
    if only_a or only_b or (not ious and (n_a or n_b)):
        reasons.append('unmatched')
    if ious and iou_min < iou_gate:
        reasons.append('iou')
    if conf_deltas and conf_max > conf_gate:
        reasons.append('conf')

    return {
        'boxes_a': int(n_a),
        'boxes_b': int(n_b),
        'matched': len(ious),
        'iou_min': iou_min,
        'iou_mean': iou_mean,
        'conf_max': conf_max,
        'only_a': int(only_a),
        'only_b': int(only_b),
        'passed': not reasons,
        'reasons': reasons,
    }
