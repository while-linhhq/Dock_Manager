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


def apply_detection_settings_update(
    *,
    camera_id: int,
    payload: dict | None,
) -> None:
    """Push new detection settings to the running per-camera pipeline."""
    from app.services.pipeline_service import pipeline_service

    pipeline_service.update_camera_detection_settings(int(camera_id), payload)
