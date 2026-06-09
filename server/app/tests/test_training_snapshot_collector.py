from app.services.ai.training_snapshot_collector import format_yolo_label


def test_format_yolo_label_normalized_center_box() -> None:
    line = format_yolo_label(100, 200, 300, 400, image_width=1000, image_height=800)
    parts = line.strip().split()
    assert parts[0] == '0'
    assert abs(float(parts[1]) - 0.2) < 1e-5
    assert abs(float(parts[2]) - 0.375) < 1e-5
    assert abs(float(parts[3]) - 0.2) < 1e-5
    assert abs(float(parts[4]) - 0.25) < 1e-5
