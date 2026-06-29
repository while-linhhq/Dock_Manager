from __future__ import annotations

import logging

from app.services.storage.minio_service import parse_minio_uri, remove_object

_log = logging.getLogger(__name__)


def remove_minio_uri(raw: str | None) -> bool:
    """Best-effort delete of a single MinIO object referenced by minio:// URI."""
    uri = str(raw or '').strip()
    ref = parse_minio_uri(uri)
    if ref is None:
        return False
    try:
        remove_object(bucket=ref.bucket, object_key=ref.object_key)
        return True
    except Exception:
        _log.warning(
            'Could not remove MinIO object bucket=%s key=%s',
            ref.bucket,
            ref.object_key,
            exc_info=True,
        )
        return False


def remove_minio_uris(paths: set[str] | list[str]) -> int:
    """Delete multiple MinIO objects; returns count of successful removals."""
    removed = 0
    seen: set[str] = set()
    for raw in paths:
        uri = str(raw or '').strip()
        if not uri or uri in seen:
            continue
        seen.add(uri)
        if remove_minio_uri(uri):
            removed += 1
    return removed


def wipe_minio_prefix(relative_prefix: str) -> dict[str, int]:
    """
    Delete every object under MINIO_MEDIA_PREFIX + relative_prefix in the configured bucket.
    Returns scanned/removed counts (best-effort).
    """
    from app.core.config import settings
    from app.services.storage.minio_service import get_minio_client

    bucket = str(getattr(settings, 'MINIO_BUCKET', '') or '').strip()
    if not bucket:
        return {'scanned': 0, 'removed': 0}

    media_prefix = str(getattr(settings, 'MINIO_MEDIA_PREFIX', '') or '').strip().strip('/')
    core = str(relative_prefix or '').strip().strip('/')
    prefix = f'{media_prefix}/{core}/' if media_prefix and core else f'{core}/' if core else ''
    if media_prefix and not core:
        prefix = f'{media_prefix}/'

    client = get_minio_client()
    scanned = 0
    removed = 0
    try:
        for obj in client.list_objects(bucket, prefix=prefix, recursive=True):
            scanned += 1
            try:
                client.remove_object(bucket, obj.object_name)
                removed += 1
            except Exception:
                _log.warning(
                    'Could not remove MinIO object bucket=%s key=%s',
                    bucket,
                    obj.object_name,
                    exc_info=True,
                )
    except Exception:
        _log.warning(
            'MinIO prefix sweep failed bucket=%s prefix=%s',
            bucket,
            prefix,
            exc_info=True,
        )
    return {'scanned': scanned, 'removed': removed}
