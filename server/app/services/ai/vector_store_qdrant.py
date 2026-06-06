from __future__ import annotations

import logging
import uuid
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


class QdrantVectorStore:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        api_key: str | None,
        collection_name: str,
        vector_size: int,
        distance: str = 'COSINE',
    ) -> None:
        self._host = str(host).strip()
        self._port = int(port)
        self._api_key = str(api_key or '').strip() or None
        self._collection_name = str(collection_name).strip()
        self._vector_size = max(1, int(vector_size))
        self._distance = str(distance or 'COSINE').strip().upper()
        self._client = None
        self._healthy = False
        self._init_client()

    @property
    def healthy(self) -> bool:
        return self._healthy and self._client is not None

    def _init_client(self) -> None:
        try:
            from qdrant_client import QdrantClient, models
        except Exception:
            logger.warning('qdrant-client package unavailable; vector store disabled')
            return
        try:
            self._client = QdrantClient(
                host=self._host,
                port=self._port,
                api_key=self._api_key,
                timeout=3.0,
            )
            self._healthy = bool(self._client.collection_exists(self._collection_name))
            if not self._healthy:
                distance = getattr(models.Distance, self._distance, models.Distance.COSINE)
                self._client.create_collection(
                    collection_name=self._collection_name,
                    vectors_config=models.VectorParams(size=self._vector_size, distance=distance),
                )
                self._healthy = True
        except Exception:
            logger.exception('Failed to initialize Qdrant vector store')
            self._client = None
            self._healthy = False

    def collection_vector_size(self) -> int | None:
        if self._client is None:
            return None
        try:
            info = self._client.get_collection(self._collection_name)
            vectors = info.config.params.vectors
            if hasattr(vectors, 'size'):
                return int(vectors.size)
            if isinstance(vectors, dict):
                first = next(iter(vectors.values()), None)
                if first is not None and hasattr(first, 'size'):
                    return int(first.size)
        except Exception:
            logger.exception('Failed to read Qdrant collection vector size')
        return None

    def healthcheck(self) -> bool:
        if self._client is None:
            return False
        try:
            self._client.get_collection(self._collection_name)
            self._healthy = True
        except Exception:
            self._healthy = False
        return self._healthy

    def upsert(
        self,
        *,
        point_id: str,
        embedding: np.ndarray,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        if self._client is None:
            return False
        vector = np.asarray(embedding, dtype=np.float32).reshape(-1)
        if vector.shape[0] != self._vector_size:
            logger.warning(
                'Qdrant upsert skipped: vector size %s != collection %s (point_id=%s)',
                vector.shape[0],
                self._vector_size,
                point_id,
            )
            return False
        try:
            from qdrant_client import models

            self._client.upsert(
                collection_name=self._collection_name,
                points=[
                    models.PointStruct(
                        id=str(point_id),
                        vector=vector.tolist(),
                        payload=payload or {},
                    )
                ],
                wait=True,
            )
            return True
        except Exception:
            logger.exception('Qdrant upsert failed point_id=%s', point_id)
            return False

    def search(
        self,
        *,
        embedding: np.ndarray,
        top_k: int,
        score_threshold: float | None = None,
        query_filter: Any | None = None,
    ) -> list[dict[str, Any]]:
        if self._client is None:
            return []
        vector = np.asarray(embedding, dtype=np.float32).reshape(-1)
        if vector.shape[0] != self._vector_size:
            return []
        try:
            response = self._client.query_points(
                collection_name=self._collection_name,
                query=vector.tolist(),
                limit=max(1, int(top_k)),
                score_threshold=score_threshold,
                query_filter=query_filter,
                with_payload=True,
            )
            out: list[dict[str, Any]] = []
            for point in response.points:
                out.append(
                    {
                        'id': str(point.id),
                        'score': float(point.score),
                        'payload': dict(point.payload or {}),
                    }
                )
            return out
        except Exception:
            logger.exception('Qdrant search failed')
            return []

    def list_by_ship_id(
        self,
        *,
        ship_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if self._client is None:
            return []
        try:
            from qdrant_client import models
        except Exception:
            return []
        try:
            points, _ = self._client.scroll(
                collection_name=self._collection_name,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key='ship_id',
                            match=models.MatchValue(value=str(ship_id)),
                        )
                    ]
                ),
                limit=max(1, int(limit)),
                with_payload=True,
                with_vectors=False,
            )
            out: list[dict[str, Any]] = []
            for point in points:
                out.append({'id': str(point.id), 'payload': dict(point.payload or {})})
            return out
        except Exception:
            logger.exception('Qdrant list_by_ship_id failed ship_id=%s', ship_id)
            return []

    def delete_point(self, *, point_id: str) -> bool:
        if self._client is None:
            return False
        try:
            from qdrant_client import models

            raw_id = str(point_id).strip()
            try:
                point_ids: list[str | uuid.UUID] = [uuid.UUID(raw_id)]
            except ValueError:
                point_ids = [raw_id]

            self._client.delete(
                collection_name=self._collection_name,
                points_selector=models.PointIdsList(points=point_ids),
                wait=True,
            )
            return True
        except Exception:
            logger.exception('Qdrant delete_point failed point_id=%s', point_id)
            return False
