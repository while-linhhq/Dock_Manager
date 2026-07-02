from __future__ import annotations

import mimetypes
from dataclasses import dataclass
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
    - s3://bucket/path/to/object.jpg
    - minio://bucket/path/to/object.jpg  (legacy)
    """
    value = (raw or '').strip()
    lower = value.lower()
    if lower.startswith('s3://'):
        rest = value[5:]
    elif lower.startswith('minio://'):
        rest = value[8:]
    else:
        return None
    if not rest or '/' not in rest:
        return None
    bucket, key = rest.split('/', 1)
    bucket = bucket.strip()
    key = key.strip()
    if not bucket or not key:
        return None
    return MinioObjectRef(bucket=bucket, object_key=key)


import threading

_s3_client = None
_s3_client_lock = threading.Lock()


def get_s3_client():
    """Return a process-wide cached boto3 S3 client.

    boto3.client() parses the botocore service model + builds a connection pool
    and event system on every call; creating one per upload (hot path) churns
    RAM and is slow. Cache one thread-safe client for the process lifetime.
    botocore clients are thread-safe for concurrent calls.
    """
    global _s3_client
    if _s3_client is not None:
        return _s3_client
    with _s3_client_lock:
        if _s3_client is not None:
            return _s3_client
        import boto3

        region = str(getattr(settings, 'AWS_REGION', '') or 'us-east-1').strip()
        access_key = str(getattr(settings, 'AWS_ACCESS_KEY_ID', '') or '').strip()
        secret_key = str(getattr(settings, 'AWS_SECRET_ACCESS_KEY', '') or '').strip()

        kwargs = {'region_name': region}
        if access_key and secret_key:
            kwargs['aws_access_key_id'] = access_key
            kwargs['aws_secret_access_key'] = secret_key

        _s3_client = boto3.client('s3', **kwargs)
        return _s3_client


# Alias — callers that import get_minio_client still work
get_minio_client = get_s3_client


def guess_content_type(object_key: str, default: str = 'application/octet-stream') -> str:
    guessed, _ = mimetypes.guess_type(object_key)
    return guessed or default


def presign_get(s3_uri: str, ttl_seconds: int = 300) -> Optional[str]:
    ref = parse_minio_uri(s3_uri)
    if ref is None:
        return None
    client = get_s3_client()
    return client.generate_presigned_url(
        'get_object',
        Params={'Bucket': ref.bucket, 'Key': ref.object_key},
        ExpiresIn=max(30, int(ttl_seconds)),
    )


def get_object_bytes(s3_uri: str) -> Optional[bytes]:
    ref = parse_minio_uri(s3_uri)
    if ref is None:
        return None
    client = get_s3_client()
    response = client.get_object(Bucket=ref.bucket, Key=ref.object_key)
    return response['Body'].read()


def open_object_stream(s3_uri: str):
    """Return (body_stream, content_type). Caller must close when done."""
    ref = parse_minio_uri(s3_uri)
    if ref is None:
        return None, None
    client = get_s3_client()
    response = client.get_object(Bucket=ref.bucket, Key=ref.object_key)
    content_type = response.get('ContentType') or guess_content_type(ref.object_key)
    return response['Body'], content_type


def get_object_size(s3_uri: str) -> int | None:
    ref = parse_minio_uri(s3_uri)
    if ref is None:
        return None
    client = get_s3_client()
    try:
        head = client.head_object(Bucket=ref.bucket, Key=ref.object_key)
        return int(head['ContentLength'])
    except Exception:
        return None


def open_object_stream_range(s3_uri: str, *, offset: int, length: int):
    ref = parse_minio_uri(s3_uri)
    if ref is None:
        return None, None
    client = get_s3_client()
    range_header = f'bytes={offset}-{offset + length - 1}'
    response = client.get_object(Bucket=ref.bucket, Key=ref.object_key, Range=range_header)
    content_type = response.get('ContentType') or guess_content_type(ref.object_key)
    return response['Body'], content_type


def put_file(
    *,
    local_path: str,
    bucket: str,
    object_key: str,
    content_type: str,
) -> Tuple[str, Optional[str]]:
    """Returns (etag, version_id)."""
    client = get_s3_client()
    with open(local_path, 'rb') as f:
        response = client.put_object(
            Bucket=bucket,
            Key=object_key,
            Body=f,
            ContentType=content_type,
        )
    etag = response.get('ETag', '').strip('"')
    version_id = response.get('VersionId')
    return etag, version_id


def put_bytes(
    *,
    data: bytes,
    bucket: str,
    object_key: str,
    content_type: str,
) -> Tuple[str, Optional[str]]:
    """Upload in-memory bytes. Returns (etag, version_id)."""
    client = get_s3_client()
    response = client.put_object(
        Bucket=bucket,
        Key=object_key,
        Body=BytesIO(data),
        ContentLength=len(data),
        ContentType=content_type,
    )
    etag = response.get('ETag', '').strip('"')
    version_id = response.get('VersionId')
    return etag, version_id


def copy_object_same_bucket(*, bucket: str, src_key: str, dest_key: str) -> None:
    if src_key == dest_key:
        return
    client = get_s3_client()
    client.copy_object(
        Bucket=bucket,
        CopySource={'Bucket': bucket, 'Key': src_key},
        Key=dest_key,
    )


def remove_object(*, bucket: str, object_key: str) -> None:
    client = get_s3_client()
    client.delete_object(Bucket=bucket, Key=object_key)
