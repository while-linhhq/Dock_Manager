"""S3 connectivity + layout audit."""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import settings
from app.services.storage.minio_layout import audit_bucket_keys, classify_object_key
from app.services.storage.s3_service import get_s3_client

_log = logging.getLogger('app.storage.minio_probe')


def probe_minio(*, list_prefix: str = 'detections/', max_list: int = 5000) -> dict[str, Any]:
    bucket = str(getattr(settings, 'MINIO_BUCKET', '') or 'media')
    client = get_s3_client()
    keys: list[str] = []
    final_samples: list[str] = []
    legacy_samples: list[str] = []
    staging_samples: list[str] = []

    paginator = client.get_paginator('list_objects_v2')
    for page in paginator.paginate(Bucket=bucket, Prefix=list_prefix):
        for obj in page.get('Contents', []):
            key = obj['Key']
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
        if len(keys) >= max_list:
            break

    counts = audit_bucket_keys(keys)
    return {
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
