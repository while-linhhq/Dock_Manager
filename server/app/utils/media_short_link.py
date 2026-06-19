"""Self-hosted short URLs for Zalo media links."""
from __future__ import annotations

from typing import Optional

from app.core.config import settings
from app.db.session import SessionLocal
from app.repositories.media_short_link_repository import media_short_link_repo

ZALO_WEBHOOK_MEDIA_PREFIX = '/api/v1/zalo/webhook/media'
ZALO_MEDIA_ORIGIN_PREFIX = '/api/v1/zalo/media/origin'


def _public_base() -> str:
    return str(settings.ZALO_PUBLIC_BASE_URL or '').strip().rstrip('/')


def normalize_short_link_code(raw: str) -> str:
    code = str(raw or '').strip()
    lower = code.lower()
    for ext in ('.jpeg', '.jpg', '.png', '.webp', '.mp4', '.webm'):
        if lower.endswith(ext):
            return code[: -len(ext)]
    return code


def _suffix_for_path(minio_path: str) -> str:
    path_lower = str(minio_path or '').lower()
    if path_lower.endswith('.mp4') or path_lower.endswith('.webm'):
        return '.mp4'
    if path_lower.endswith('.jpg') or path_lower.endswith('.jpeg'):
        return '.jpg'
    if path_lower.endswith('.png'):
        return '.png'
    return ''


def build_short_media_url(minio_path: str, *, ttl_hours: int = 24) -> Optional[str]:
    """Legacy public media URL (/api/v1/media/v/...). Prefer build_zalo_short_media_url for Zalo."""
    base = _public_base()
    path = (minio_path or '').strip()
    if not base or not path:
        return None

    db = SessionLocal()
    try:
        row = media_short_link_repo.create(db, minio_path=path, ttl_hours=ttl_hours)
    finally:
        db.close()

    suffix = _suffix_for_path(path)
    return f'{base}/api/v1/media/v/{row.code}{suffix}'


def build_zalo_short_media_url(
    minio_path: str,
    *,
    ttl_hours: int | None = None,
    cache_bust: bool = False,
) -> Optional[str]:
    """
    Short URL under /api/v1/zalo/webhook/media/ so Cloudflare Worker on webhook* can proxy
    Zalo's Java/1.8.0_192 User-Agent fetches.
    """
    base = _public_base()
    path = (minio_path or '').strip()
    if not base or not path:
        return None

    hours = int(ttl_hours if ttl_hours is not None else settings.ZALO_MEDIA_TTL_HOURS)
    db = SessionLocal()
    try:
        row = media_short_link_repo.create(db, minio_path=path, ttl_hours=hours)
    finally:
        db.close()

    suffix = _suffix_for_path(path)
    url = f'{base}{ZALO_WEBHOOK_MEDIA_PREFIX}/v/{row.code}{suffix}'
    if cache_bust:
        import time

        url = f'{url}?v={int(time.time())}'
    return url


def resolve_short_media_path(code: str) -> Optional[str]:
    raw = normalize_short_link_code(code)
    if not raw:
        return None
    db = SessionLocal()
    try:
        row = media_short_link_repo.get_active(db, raw)
        return str(row.minio_path) if row else None
    finally:
        db.close()
