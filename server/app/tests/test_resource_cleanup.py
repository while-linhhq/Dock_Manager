"""Unit tests for detection and vessel resource cleanup."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.detection_cleanup_service import _collect_detection_media_paths


def test_collect_detection_media_paths_deduplicates() -> None:
    detection = SimpleNamespace(
        audit_image_path='minio://media/detections/01-01-2026/1/images/a.jpg',
        video_path='minio://media/detections/01-01-2026/1/videos/b.mp4',
        media=[
            SimpleNamespace(file_path='minio://media/detections/01-01-2026/1/images/a.jpg'),
            SimpleNamespace(file_path='minio://media/detections/01-01-2026/1/images/c.jpg'),
            SimpleNamespace(file_path='/local/not-minio.jpg'),
        ],
    )
    paths = _collect_detection_media_paths(detection)
    assert paths == {
        'minio://media/detections/01-01-2026/1/images/a.jpg',
        'minio://media/detections/01-01-2026/1/videos/b.mp4',
        'minio://media/detections/01-01-2026/1/images/c.jpg',
    }
