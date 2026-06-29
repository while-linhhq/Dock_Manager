from app.services.ai.detection_filter import (
    DEFAULT_MIN_BBOX_HEIGHT,
    DEFAULT_MIN_BBOX_WIDTH,
    filter_boxes_by_min_size,
    parse_min_bbox_from_detection_settings,
)


def test_parse_min_bbox_defaults_when_null():
    assert parse_min_bbox_from_detection_settings(None) == (
        DEFAULT_MIN_BBOX_WIDTH,
        DEFAULT_MIN_BBOX_HEIGHT,
    )


def test_parse_min_bbox_custom_values():
    assert parse_min_bbox_from_detection_settings(
        {'min_bbox_width': 80, 'min_bbox_height': 40}
    ) == (80, 40)


def test_parse_min_bbox_clamps_to_one():
    assert parse_min_bbox_from_detection_settings(
        {'min_bbox_width': 0, 'min_bbox_height': -5}
    ) == (1, 1)


def test_filter_boxes_keeps_large_enough():
    boxes = [[0, 0, 60, 40]]
    confs = [0.9]
    kept_boxes, kept_confs = filter_boxes_by_min_size(boxes, confs, 50, 30)
    assert kept_boxes == boxes
    assert kept_confs == confs


def test_filter_boxes_drops_small_width():
    boxes = [[0, 0, 40, 40]]
    confs = [0.9]
    kept_boxes, kept_confs = filter_boxes_by_min_size(boxes, confs, 50, 30)
    assert kept_boxes == []
    assert kept_confs == []


def test_filter_boxes_drops_small_height():
    boxes = [[0, 0, 60, 20]]
    confs = [0.8]
    kept_boxes, kept_confs = filter_boxes_by_min_size(boxes, confs, 50, 30)
    assert kept_boxes == []
    assert kept_confs == []


def test_filter_boxes_keeps_at_threshold():
    boxes = [[0, 0, 50, 30]]
    confs = [0.7]
    kept_boxes, kept_confs = filter_boxes_by_min_size(boxes, confs, 50, 30)
    assert kept_boxes == boxes
    assert kept_confs == confs


def test_filter_boxes_empty_input():
    assert filter_boxes_by_min_size([], [], 50, 30) == ([], [])
