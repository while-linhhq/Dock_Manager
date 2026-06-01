from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from io import BytesIO
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


def get_object_bytes(minio_uri: str) -> Optional[bytes]:
    ref = parse_minio_uri(minio_uri)
    if ref is None:
        return None
    client = get_minio_client()
    response = client.get_object(ref.bucket, ref.object_key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


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


def put_bytes(
    *,
    data: bytes,
    bucket: str,
    object_key: str,
    content_type: str,
) -> Tuple[str, Optional[str]]:
    """
    Upload in-memory bytes and return (etag, version_id).
    """
    client = get_minio_client()
    res = client.put_object(
        bucket,
        object_key,
        BytesIO(data),
        length=len(data),
        content_type=content_type,
    )
    return res.etag, getattr(res, 'version_id', None)


def copy_object_same_bucket(*, bucket: str, src_key: str, dest_key: str) -> None:
    """Server-side copy within the same bucket (S3 CopyObject)."""
    if src_key == dest_key:
        return
    from minio.commonconfig import CopySource
    from minio.error import S3Error

    client = get_minio_client()
    try:
        client.copy_object(bucket, dest_key, CopySource(bucket, src_key))
        return
    except S3Error as exc:
        # Some reverse proxies/tunnels can reject x-amz-copy-source with AccessDenied
        # even when normal GET/PUT with the same credentials is allowed.
        if exc.code != 'AccessDenied':
            raise

    response = client.get_object(bucket, src_key)
    try:
        client.put_object(
            bucket,
            dest_key,
            data=response,
            length=-1,
            part_size=10 * 1024 * 1024,
        )
    finally:
        response.close()
        response.release_conn()


def remove_object(*, bucket: str, object_key: str) -> None:
    client = get_minio_client()
    client.remove_object(bucket, object_key)

