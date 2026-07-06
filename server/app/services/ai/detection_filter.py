from __future__ import annotations

DEFAULT_MIN_BBOX_WIDTH = 50
DEFAULT_MIN_BBOX_HEIGHT = 30


def parse_min_bbox_from_detection_settings(payload: dict | None) -> tuple[int, int]:
    """Read per-camera min bbox size from cameras.detection_settings JSON."""
    if not isinstance(payload, dict):
        return DEFAULT_MIN_BBOX_WIDTH, DEFAULT_MIN_BBOX_HEIGHT
    try:
        min_width = int(payload.get('min_bbox_width', DEFAULT_MIN_BBOX_WIDTH))
    except (TypeError, ValueError):
        min_width = DEFAULT_MIN_BBOX_WIDTH
    try:
        min_height = int(payload.get('min_bbox_height', DEFAULT_MIN_BBOX_HEIGHT))
    except (TypeError, ValueError):
        min_height = DEFAULT_MIN_BBOX_HEIGHT
    return max(1, min_width), max(1, min_height)


def filter_boxes_by_min_size(
    boxes_list: list,
    det_confs: list[float],
    min_width: int,
    min_height: int,
) -> tuple[list, list[float]]:
    """Drop detections smaller than min_width x min_height (pixel, AND logic)."""
    if not boxes_list:
        return boxes_list, det_confs
    min_w = max(1, int(min_width))
    min_h = max(1, int(min_height))
    filtered_boxes: list = []
    filtered_confs: list[float] = []
    for box, conf in zip(boxes_list, det_confs):
        width = int(box[2]) - int(box[0])
        height = int(box[3]) - int(box[1])
        if width >= min_w and height >= min_h:
            filtered_boxes.append(box)
            filtered_confs.append(conf)
    return filtered_boxes, filtered_confs


def _iomin(a, b) -> float:
    """Intersection over the smaller box area (containment-sensitive overlap).

    Unlike IoU, this returns ~1.0 when one box is fully inside another, so it
    catches duplicate detections that YOLO's plain-IoU NMS lets through
    (nested/contained boxes have low IoU but high IoMin).
    """
    ax1, ay1, ax2, ay2 = float(a[0]), float(a[1]), float(a[2]), float(a[3])
    bx1, by1, bx2, by2 = float(b[0]), float(b[1]), float(b[2]), float(b[3])
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0.0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    smaller = min(area_a, area_b)
    if smaller <= 0.0:
        return 0.0
    return inter / smaller


def dedup_overlapping_boxes(
    boxes_list: list,
    det_confs: list[float],
    iomin_threshold: float,
) -> tuple[list, list[float]]:
    """Suppress a box that overlaps a higher-confidence box with IoMin >= threshold.

    One physical ship sometimes yields two YOLO boxes (a hull box + a smaller
    contained box, or a bow/stern split) whose mutual IoU is below the NMS
    threshold, so both survive and the tracker spawns two tracks for it. This
    greedy pass keeps the highest-confidence box and drops any later box whose
    intersection-over-min-area with an already-kept box crosses the threshold.
    ``iomin_threshold <= 0`` disables the pass (returns input unchanged).
    """
    if iomin_threshold <= 0.0 or len(boxes_list) < 2:
        return boxes_list, det_confs
    order = sorted(range(len(boxes_list)), key=lambda i: det_confs[i], reverse=True)
    kept_idx: list[int] = []
    for i in order:
        bi = boxes_list[i]
        suppressed = False
        for k in kept_idx:
            if _iomin(bi, boxes_list[k]) >= iomin_threshold:
                suppressed = True
                break
        if not suppressed:
            kept_idx.append(i)
    kept_idx.sort()
    return [boxes_list[i] for i in kept_idx], [det_confs[i] for i in kept_idx]


def apply_detection_settings_update(
    *,
    camera_id: int,
    payload: dict | None,
) -> None:
    """Push new detection settings to the running per-camera pipeline."""
    from app.services.pipeline_service import pipeline_service

    pipeline_service.update_camera_detection_settings(int(camera_id), payload)
