from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.models.detection import Detection
from app.models.invoice import Invoice
from app.models.media_short_link import MediaShortLink
from app.models.payment import Payment
from app.services.storage.media_cleanup import remove_minio_uris

_log = logging.getLogger(__name__)


def _collect_detection_media_paths(detection: Detection) -> set[str]:
    paths: set[str] = set()
    for attr in ('audit_image_path', 'video_path'):
        raw = str(getattr(detection, attr, '') or '').strip()
        if raw.startswith('minio://'):
            paths.add(raw)

    for media in getattr(detection, 'media', None) or []:
        raw = str(getattr(media, 'file_path', '') or '').strip()
        if raw.startswith('minio://'):
            paths.add(raw)
    return paths


def _hard_delete_invoice(db: Session, invoice_id: int) -> None:
    db.query(Payment).filter(Payment.invoice_id == invoice_id).delete(synchronize_session=False)
    db.query(Invoice).filter(Invoice.id == invoice_id).delete(synchronize_session=False)


def _delete_media_short_links(db: Session, minio_paths: set[str]) -> int:
    if not minio_paths:
        return 0
    return (
        db.query(MediaShortLink)
        .filter(MediaShortLink.minio_path.in_(sorted(minio_paths)))
        .delete(synchronize_session=False)
    )


def purge_detection_resources(db: Session, detection_id: int) -> dict[str, Any]:
    """
    Delete all resources tied to a detection before removing the DB row:
    MinIO media, linked invoices (hard delete), and short-link rows.
    """
    detection = (
        db.query(Detection)
        .options(joinedload(Detection.media))
        .filter(Detection.id == detection_id)
        .first()
    )
    if detection is None:
        return {'found': False}

    media_paths = _collect_detection_media_paths(detection)
    invoice_rows = (
        db.query(Invoice.id)
        .filter(Invoice.detection_id == detection_id)
        .all()
    )
    invoice_ids = [int(row[0]) for row in invoice_rows]

    minio_removed = remove_minio_uris(media_paths)
    short_links_removed = _delete_media_short_links(db, media_paths)

    for invoice_id in invoice_ids:
        _hard_delete_invoice(db, invoice_id)

    db.delete(detection)
    db.commit()

    summary = {
        'found': True,
        'detection_id': detection_id,
        'minio_paths': len(media_paths),
        'minio_removed': minio_removed,
        'invoices_deleted': len(invoice_ids),
        'short_links_deleted': short_links_removed,
    }
    _log.info('Detection purge complete %s', summary)
    return summary
