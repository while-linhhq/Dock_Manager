#!/usr/bin/env python3
"""
Re-embed vessel visual references from stored preview images into the current Qdrant collection.

Usage (from server/):
  python scripts/reembed_visual_references.py
  python scripts/reembed_visual_references.py --source-collection vessel_visual_embeddings
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import cv2
import numpy as np

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from app.services.vessel_visual_reference_service import (
    LOCAL_PREVIEW_ROOT,
    LOCAL_PREVIEW_URI_PREFIX,
    local_preview_path,
)
from app.core.config import settings
from app.services.ai.vector_store_qdrant import QdrantVectorStore
from app.services.ai.visual_embedding_factory import get_visual_embedding_extractor
from app.services.storage.minio_service import get_object_bytes, parse_minio_uri

logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
_log = logging.getLogger('reembed_visual_references')


def _load_preview_bgr(*, ship_id: str, point_id: str, preview_uri: str | None) -> np.ndarray | None:
    uri = str(preview_uri or '').strip()
    if uri.startswith('minio://'):
        data = get_object_bytes(uri)
        if data:
            arr = np.frombuffer(data, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is not None and frame.size > 0:
                return frame

    if uri.startswith(LOCAL_PREVIEW_URI_PREFIX):
        rel = uri[len(LOCAL_PREVIEW_URI_PREFIX) :]
        path = LOCAL_PREVIEW_ROOT / rel
        if path.is_file():
            frame = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
            if frame is not None and frame.size > 0:
                return frame

    path = local_preview_path(ship_id, point_id)
    if path.is_file():
        frame = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is not None and frame.size > 0:
            return frame
    return None


def reembed(*, source_collection: str | None) -> None:
    extractor = get_visual_embedding_extractor()
    if extractor.backend == 'unavailable':
        raise RuntimeError('Visual embedding extractor is unavailable')

    vector_size = extractor.vector_dim
    target = QdrantVectorStore(
        host=settings.QDRANT_HOST,
        port=int(settings.QDRANT_PORT),
        api_key=settings.QDRANT_API_KEY or None,
        collection_name=settings.QDRANT_COLLECTION,
        vector_size=vector_size,
        distance=settings.QDRANT_DISTANCE,
    )
    if not target.healthcheck():
        raise RuntimeError(f'Target Qdrant collection unavailable: {settings.QDRANT_COLLECTION}')

    source_name = source_collection or 'vessel_visual_embeddings'
    if source_name == settings.QDRANT_COLLECTION:
        source = target
    else:
        source = QdrantVectorStore(
            host=settings.QDRANT_HOST,
            port=int(settings.QDRANT_PORT),
            api_key=settings.QDRANT_API_KEY or None,
            collection_name=source_name,
            vector_size=max(vector_size, int(settings.QDRANT_VECTOR_SIZE)),
            distance=settings.QDRANT_DISTANCE,
        )
        if not source.healthcheck():
            _log.warning('Source collection %s unavailable; nothing to migrate', source_name)
            return

    offset = None
    migrated = 0
    skipped = 0
    while True:
        points, offset = source.scroll_all(limit=128, offset=offset)
        if not points:
            break
        for point in points:
            point_id = str(point.get('id') or '')
            payload = dict(point.get('payload') or {})
            ship_id = str(payload.get('ship_id') or '')
            preview_uri = str(payload.get('preview_uri') or '') or None
            frame = _load_preview_bgr(ship_id=ship_id, point_id=point_id, preview_uri=preview_uri)
            if frame is None:
                skipped += 1
                _log.warning('Skip point=%s ship=%s (no preview)', point_id, ship_id)
                continue
            embedding = extractor.extract(frame)
            if embedding is None:
                skipped += 1
                continue
            ok = target.upsert(point_id=point_id, embedding=embedding, payload=payload)
            if ok:
                migrated += 1
            else:
                skipped += 1
        if offset is None:
            break

    _log.info('Re-embed complete migrated=%s skipped=%s target=%s', migrated, skipped, settings.QDRANT_COLLECTION)


def main() -> None:
    parser = argparse.ArgumentParser(description='Re-embed vessel visual references with DINOv2')
    parser.add_argument(
        '--source-collection',
        default='vessel_visual_embeddings',
        help='Legacy Qdrant collection to read points from',
    )
    args = parser.parse_args()
    reembed(source_collection=args.source_collection)


if __name__ == '__main__':
    main()
