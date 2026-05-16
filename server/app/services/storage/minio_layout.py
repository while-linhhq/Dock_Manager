"""Canonical MinIO object keys for detection media (bucket: settings.MINIO_BUCKET)."""

from __future__ import annotations

import re
from typing import Iterable

from app.core.config import settings

# detections/{DD-MM-YYYY}/{detection_id}/videos|images/...
FINAL_VIDEO_RE = re.compile(
    r'^detections/\d{2}-\d{2}-\d{4}/\d+/videos/(fused_|single_).+\.mp4$'
)
FINAL_IMAGE_RE = re.compile(
    r'^detections/\d{2}-\d{2}-\d{4}/\d+/images/'
    r'(fused_best_detection_|fused_best_ocr_|single_best_detection_|single_best_ocr_).+\.jpg$'
)
STAGING_VIDEO_RE = re.compile(
    r'^detections/staging/\d{2}-\d{2}-\d{4}/videos/(fused_|single_).+\.mp4$'
)
# Legacy layout (pre-refactor) — should not be written by current pipeline.
LEGACY_OBJECT_RE = re.compile(
    r'^detections/\d+/(video|image)/.+'
)


def _safe_segment(raw: str) -> str:
    return ''.join(ch if ch.isalnum() or ch in ('-', '_', '.') else '_' for ch in raw)


def prefix_key(*segments: str) -> str:
    prefix = str(getattr(settings, 'MINIO_MEDIA_PREFIX', '') or '').strip().strip('/')
    core = '/'.join(_safe_segment(str(s).strip()) for s in segments if str(s).strip())
    return f'{prefix}/{core}' if prefix else core


def staging_video_key(day_dd_mm_yyyy: str, filename: str) -> str:
    fname = filename if filename.startswith(('fused_', 'single_')) else f'fused_{filename}'
    return prefix_key('detections', 'staging', day_dd_mm_yyyy, 'videos', fname)


def final_video_key(day_dd_mm_yyyy: str, detection_id: int, filename: str) -> str:
    return prefix_key('detections', day_dd_mm_yyyy, str(detection_id), 'videos', filename)


def final_image_key(day_dd_mm_yyyy: str, detection_id: int, filename: str) -> str:
    return prefix_key('detections', day_dd_mm_yyyy, str(detection_id), 'images', filename)


def classify_object_key(object_key: str) -> str:
    key = object_key.lstrip('/')
    if FINAL_VIDEO_RE.match(key) or FINAL_IMAGE_RE.match(key):
        return 'final'
    if STAGING_VIDEO_RE.match(key):
        return 'staging_video'
    if LEGACY_OBJECT_RE.match(key):
        return 'legacy'
    if key.startswith('detections/staging/'):
        return 'staging_other'
    return 'other'


def audit_bucket_keys(object_keys: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {'final': 0, 'staging_video': 0, 'legacy': 0, 'staging_other': 0, 'other': 0}
    for raw in object_keys:
        counts[classify_object_key(raw)] = counts.get(classify_object_key(raw), 0) + 1
    return counts
