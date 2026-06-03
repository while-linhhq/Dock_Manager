"""Qdrant delete_point must accept UUID point IDs (not legacy dict selector)."""

from __future__ import annotations

import uuid

import numpy as np

from app.core.config import settings
from app.services.ai.vector_store_qdrant import QdrantVectorStore


def test_delete_point_accepts_uuid_string() -> None:
    store = QdrantVectorStore(
        host=settings.QDRANT_HOST,
        port=int(settings.QDRANT_PORT),
        api_key=settings.QDRANT_API_KEY or None,
        collection_name=settings.QDRANT_COLLECTION,
        vector_size=int(settings.QDRANT_VECTOR_SIZE),
        distance=settings.QDRANT_DISTANCE,
    )
    if not store.healthcheck():
        return

    point_id = str(uuid.uuid4())
    vector = np.random.randn(store._vector_size).astype(np.float32)
    vector /= max(float(np.linalg.norm(vector)), 1e-8)

    store.upsert(
        point_id=point_id,
        embedding=vector,
        payload={'ship_id': 'TEST-DELETE-POINT', 'source': 'pytest'},
    )
    assert store.delete_point(point_id=point_id) is True

    remaining = store.list_by_ship_id(ship_id='TEST-DELETE-POINT', limit=10)
    assert all(str(item['id']) != point_id for item in remaining)
