"""MinIO connectivity + layout audit via S3 API (port 9100 in docker-compose)."""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import settings
from app.services.storage.minio_layout import audit_bucket_keys, classify_object_key
from app.services.storage.minio_service import get_minio_client

_log = logging.getLogger('app.storage.minio_probe')


def probe_minio(*, list_prefix: str = 'detections/', max_list: int = 5000) -> dict[str, Any]:
    """
    List objects through MinIO S3 API (MINIO_ENDPOINT, typically :9100).
    Console UI is on :9101 — same bucket, not a second store.
    """
    endpoint = str(getattr(settings, 'MINIO_ENDPOINT', '') or '')
    bucket = str(getattr(settings, 'MINIO_BUCKET', '') or 'media')
    client = get_minio_client()
    keys: list[str] = []
    final_samples: list[str] = []
    legacy_samples: list[str] = []
    staging_samples: list[str] = []

    for obj in client.list_objects(bucket, prefix=list_prefix, recursive=True):
        key = obj.object_name
        keys.append(key)
        kind = classify_object_key(key)
        if kind == 'final' and len(final_samples) < 8:
            final_samples.append(key)
        elif kind == 'legacy' and len(legacy_samples) < 5:
            legacy_samples.append(key)
        elif kind.startswith('staging') and len(staging_samples) < 5:
            staging_samples.append(key)
        if len(keys) >= max_list:
            break

    counts = audit_bucket_keys(keys)
    return {
        'endpoint': endpoint,
        'bucket': bucket,
        'listed': len(keys),
        'counts': counts,
        'final_samples': final_samples,
        'legacy_samples': legacy_samples,
        'staging_samples': staging_samples,
    }


def log_minio_probe_at_startup() -> None:
    """Legacy entrypoint — prefer ``app.core.startup_report.run_startup_checks``."""
    from app.core.startup_report import _check_minio

    _check_minio()
