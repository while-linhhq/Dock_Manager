from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Optional, Tuple

from app.core.config import settings


@dataclass(frozen=True)
class MinioObjectRef:
    bucket: str
    object_key: str


def parse_minio_uri(raw: str) -> Optional[MinioObjectRef]:
    """
    Supported formats:
    - minio://bucket/path/to/object.jpg
    """
    value = (raw or '').strip()
    if not value.lower().startswith('minio://'):
        return None
    rest = value[len('minio://') :]
    if not rest or '/' not in rest:
        return None
    bucket, key = rest.split('/', 1)
    bucket = bucket.strip()
    key = key.strip()
    if not bucket or not key:
        return None
    return MinioObjectRef(bucket=bucket, object_key=key)


def _build_endpoint() -> str:
    endpoint = str(getattr(settings, 'MINIO_ENDPOINT', '') or '').strip()
    if not endpoint:
        return '127.0.0.1:9000'
    endpoint = endpoint.replace('http://', '').replace('https://', '')
    return endpoint


def _to_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    raw = str(value or '').strip().lower()
    if raw in ('1', 'true', 'yes', 'y', 'on'):
        return True
    if raw in ('0', 'false', 'no', 'n', 'off'):
        return False
    return default


def get_minio_client():
    from minio import Minio

    return Minio(
        _build_endpoint(),
        access_key=str(getattr(settings, 'MINIO_ACCESS_KEY', '') or ''),
        secret_key=str(getattr(settings, 'MINIO_SECRET_KEY', '') or ''),
        secure=_to_bool(getattr(settings, 'MINIO_SECURE', False), default=False),
    )


def presign_get(minio_uri: str, ttl_seconds: int = 300) -> Optional[str]:
    ref = parse_minio_uri(minio_uri)
    if ref is None:
        return None
    client = get_minio_client()
    return client.presigned_get_object(
        ref.bucket,
        ref.object_key,
        expires=timedelta(seconds=max(30, int(ttl_seconds))),
    )


def put_file(
    *,
    local_path: str,
    bucket: str,
    object_key: str,
    content_type: str,
) -> Tuple[str, Optional[str]]:
    """
    Returns (etag, version_id).
    """
    client = get_minio_client()
    res = client.fput_object(
        bucket,
        object_key,
        local_path,
        content_type=content_type,
    )
    return res.etag, getattr(res, 'version_id', None)

