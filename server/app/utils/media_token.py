"""Signed JWT tokens for public media preview URLs (Zalo Bot inline images)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt

from app.core.config import settings

_MEDIA_TOKEN_TYPE = 'media_preview'


def create_media_preview_token(minio_path: str, *, ttl_hours: int = 24) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=max(1, int(ttl_hours)))
    payload = {
        'typ': _MEDIA_TOKEN_TYPE,
        'path': (minio_path or '').strip(),
        'exp': expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_media_preview_token(token: str) -> Optional[str]:
    raw = str(token or '').strip()
    if raw.lower().endswith('.mp4'):
        raw = raw[:-4]
    try:
        payload = jwt.decode(raw, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None
    if payload.get('typ') != _MEDIA_TOKEN_TYPE:
        return None
    path = str(payload.get('path') or '').strip()
    return path or None


def build_media_view_url(
    minio_path: str,
    *,
    request: object | None = None,
    ttl_hours: int = 12,
) -> Optional[str]:
    """URL xem media trên chính origin API — mở được từ trình duyệt ở xa.

    ``presign_get`` trỏ thẳng MinIO (``MINIO_ENDPOINT``, thường là 127.0.0.1:9100)
    nên chỉ máy chủ mở được; URL này đi qua API nên trình duyệt ở đâu cũng xem được
    miễn tới được API, và token là JWT ký sẵn nên thẻ ``<img>`` không cần header
    Authorization.

    Thứ tự chọn base: ``PUBLIC_BASE_URL`` → ``ZALO_PUBLIC_BASE_URL`` → origin của
    chính request (dự phòng cho triển khai chưa cấu hình). Trả ``None`` nếu không
    xác định được base để nơi gọi giữ nguyên giá trị cũ.
    """
    path = (minio_path or '').strip()
    if not path:
        return None

    base = (
        str(getattr(settings, 'PUBLIC_BASE_URL', '') or '').strip().rstrip('/')
        or str(settings.ZALO_PUBLIC_BASE_URL or '').strip().rstrip('/')
    )
    if not base and request is not None:
        base = str(getattr(request, 'base_url', '') or '').strip().rstrip('/')
    if not base:
        return None

    token = create_media_preview_token(path, ttl_hours=ttl_hours)
    suffix = '.mp4' if path.lower().endswith(('.mp4', '.webm')) else ''
    return f'{base}/api/v1/media/preview/{token}{suffix}'


def build_media_preview_url(minio_path: str, *, ttl_hours: int = 24) -> Optional[str]:
    base = str(settings.ZALO_PUBLIC_BASE_URL or '').strip().rstrip('/')
    path = (minio_path or '').strip()
    if not base or not path:
        return None
    token = create_media_preview_token(path, ttl_hours=ttl_hours)
    return f'{base}/api/v1/media/preview/{token}'


def build_zalo_media_preview_url(minio_path: str, *, ttl_hours: int | None = None) -> Optional[str]:
    """Signed preview URL under Zalo webhook media path (Cloudflare Worker proxy)."""
    base = str(settings.ZALO_PUBLIC_BASE_URL or '').strip().rstrip('/')
    path = (minio_path or '').strip()
    if not base or not path:
        return None
    hours = int(ttl_hours if ttl_hours is not None else settings.ZALO_MEDIA_TTL_HOURS)
    token = create_media_preview_token(path, ttl_hours=hours)
    return f'{base}/api/v1/zalo/webhook/media/preview/{token}'


def build_zalo_media_video_preview_url(minio_path: str, *, ttl_hours: int | None = None) -> Optional[str]:
    """Video URL with .mp4 suffix so Zalo/mobile players recognize stream type."""
    url = build_zalo_media_preview_url(minio_path, ttl_hours=ttl_hours)
    if not url:
        return None
    path_lower = minio_path.lower()
    if path_lower.endswith('.mp4') or path_lower.endswith('.webm'):
        return f'{url}.mp4'
    return url


def build_media_video_preview_url(minio_path: str, *, ttl_hours: int = 24) -> Optional[str]:
    """Legacy video preview URL (/api/v1/media/preview/...)."""
    url = build_media_preview_url(minio_path, ttl_hours=ttl_hours)
    if not url:
        return None
    path_lower = minio_path.lower()
    if path_lower.endswith('.mp4') or path_lower.endswith('.webm'):
        return f'{url}.mp4'
    return url
