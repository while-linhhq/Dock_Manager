from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.media_short_link import MediaShortLink


class MediaShortLinkRepository:
    def find_active_by_path(self, db: Session, minio_path: str) -> MediaShortLink | None:
        now = datetime.now(timezone.utc)
        return (
            db.query(MediaShortLink)
            .filter(
                MediaShortLink.minio_path == minio_path,
                MediaShortLink.expires_at > now,
            )
            .order_by(MediaShortLink.created_at.desc())
            .first()
        )

    def create(self, db: Session, *, minio_path: str, ttl_hours: int = 24) -> MediaShortLink:
        path = (minio_path or '').strip()
        if not path:
            raise ValueError('minio_path is required')

        existing = self.find_active_by_path(db, path)
        if existing is not None:
            return existing

        expires_at = datetime.now(timezone.utc) + timedelta(hours=max(1, int(ttl_hours)))
        for _ in range(5):
            code = secrets.token_urlsafe(6)[:10]
            row = MediaShortLink(code=code, minio_path=path, expires_at=expires_at)
            db.add(row)
            try:
                db.commit()
                db.refresh(row)
                return row
            except IntegrityError:
                db.rollback()
        raise RuntimeError('Failed to allocate short link code')

    def get_active(self, db: Session, code: str) -> MediaShortLink | None:
        raw = str(code or '').strip()
        if not raw:
            return None
        now = datetime.now(timezone.utc)
        return (
            db.query(MediaShortLink)
            .filter(MediaShortLink.code == raw, MediaShortLink.expires_at > now)
            .first()
        )


media_short_link_repo = MediaShortLinkRepository()
