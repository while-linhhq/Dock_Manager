from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.services.ai.vector_store_qdrant import QdrantVectorStore
from app.services.storage.media_cleanup import remove_minio_uri
from app.services.storage.s3_service import parse_minio_uri

_log = logging.getLogger(__name__)

_SERVER_ROOT = Path(__file__).resolve().parents[2]
LOCAL_PREVIEW_ROOT = _SERVER_ROOT / 'data' / 'visual-references'
LOCAL_PREVIEW_URI_PREFIX = 'local://'
_LOCAL_PREVIEW_ROOT = LOCAL_PREVIEW_ROOT
_LOCAL_PREVIEW_URI_PREFIX = LOCAL_PREVIEW_URI_PREFIX


def _get_qdrant_store() -> QdrantVectorStore:
    return QdrantVectorStore(
        host=settings.QDRANT_HOST,
        port=int(settings.QDRANT_PORT),
        api_key=settings.QDRANT_API_KEY or None,
        collection_name=settings.QDRANT_COLLECTION,
        vector_size=max(1, int(settings.QDRANT_VECTOR_SIZE)),
        distance=settings.QDRANT_DISTANCE,
    )


def _safe_path_segment(raw: str) -> str:
    cleaned = ''.join(ch if ch.isalnum() or ch in ('-', '_', '.') else '_' for ch in str(raw).strip())
    return cleaned.strip('._-') or 'unknown'


def local_preview_path(ship_id: str, point_id: str) -> Path:
    rel = f'{_safe_path_segment(ship_id)}/{_safe_path_segment(point_id)}.jpg'
    return _LOCAL_PREVIEW_ROOT / rel


def delete_visual_preview(*, ship_id: str, point_id: str, preview_uri: str | None = None) -> None:
    """Remove local and/or MinIO preview image for one visual reference point."""
    uri = str(preview_uri or '').strip()
    if uri.startswith(_LOCAL_PREVIEW_URI_PREFIX):
        rel = uri[len(_LOCAL_PREVIEW_URI_PREFIX) :]
        try:
            (_LOCAL_PREVIEW_ROOT / rel).unlink(missing_ok=True)
        except Exception:
            _log.warning('Could not remove local visual reference preview %s', rel)
        return

    ref = parse_minio_uri(uri)
    if ref is not None:
        remove_minio_uri(uri)

    try:
        local_preview_path(ship_id, point_id).unlink(missing_ok=True)
    except Exception:
        pass


def delete_visual_reference(
    *,
    ship_id: str,
    point_id: str,
    qdrant: QdrantVectorStore | None = None,
) -> bool:
    """Delete one Qdrant point and its preview assets."""
    store = qdrant or _get_qdrant_store()
    preview_uri: str | None = None
    if store.healthcheck():
        for point in store.list_by_ship_id(ship_id=str(ship_id), limit=500):
            if str(point.get('id')) == str(point_id):
                preview_uri = str((point.get('payload') or {}).get('preview_uri') or '') or None
                break
        if not store.delete_point(point_id=str(point_id)):
            return False
    delete_visual_preview(ship_id=str(ship_id), point_id=str(point_id), preview_uri=preview_uri)
    return True


def delete_all_visual_references_for_ship(*, ship_id: str) -> dict[str, Any]:
    """
    Remove every enrolled visual reference for a ship_id from Qdrant and storage.
    Returns summary counts for logging/audit.
    """
    normalized_ship_id = str(ship_id or '').strip()
    if not normalized_ship_id:
        return {'qdrant_deleted': 0, 'previews_deleted': 0}

    store = _get_qdrant_store()
    points: list[dict[str, Any]] = []
    if store.healthcheck():
        points = store.list_by_ship_id(ship_id=normalized_ship_id, limit=500)

    previews_deleted = 0
    for point in points:
        point_id = str(point.get('id') or '')
        preview_uri = str((point.get('payload') or {}).get('preview_uri') or '') or None
        delete_visual_preview(
            ship_id=normalized_ship_id,
            point_id=point_id,
            preview_uri=preview_uri,
        )
        previews_deleted += 1

    qdrant_deleted = 0
    if store.healthcheck():
        qdrant_deleted = store.delete_by_ship_id(ship_id=normalized_ship_id)

    ship_dir = _LOCAL_PREVIEW_ROOT / _safe_path_segment(normalized_ship_id)
    if ship_dir.is_dir():
        try:
            shutil.rmtree(ship_dir, ignore_errors=True)
        except Exception:
            _log.warning('Could not remove local visual reference dir %s', ship_dir)

    return {
        'ship_id': normalized_ship_id,
        'qdrant_deleted': qdrant_deleted,
        'previews_deleted': previews_deleted,
    }


def count_visual_references_by_ship_ids(ship_ids: list[str]) -> dict[str, int]:
    """Return enrolled visual reference counts keyed by ship_id."""
    normalized = [str(sid).strip() for sid in ship_ids if str(sid).strip()]
    if not normalized:
        return {}

    qdrant = _get_qdrant_store()
    if not qdrant.healthcheck():
        _log.debug('Qdrant unavailable; visual_reference_count defaults to 0')
        return {sid: 0 for sid in normalized}

    return qdrant.count_by_ship_ids(ship_ids=normalized)
