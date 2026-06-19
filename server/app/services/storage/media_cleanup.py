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
