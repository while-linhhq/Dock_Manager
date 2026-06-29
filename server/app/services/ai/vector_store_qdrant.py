from __future__ import annotations

import logging
import time
import uuid
from typing import Any

import numpy as np

from app.core.config import settings

logger = logging.getLogger(__name__)

_INIT_RETRIES = 3
_INIT_RETRY_DELAY_SEC = 2.0


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
        self._last_connect_error: str | None = None
        self._init_client()

    @property
    def healthy(self) -> bool:
        return self._healthy and self._client is not None

    def _connect_once(self) -> bool:
        """Single connect attempt; returns True when collection is ready."""
        try:
            from qdrant_client import QdrantClient, models
        except Exception:
            logger.warning('qdrant-client package unavailable; vector store disabled')
            return False

        timeout = max(1.0, float(settings.QDRANT_TIMEOUT_SEC))
        try:
            self._client = QdrantClient(
                host=self._host,
                port=self._port,
                api_key=self._api_key,
                timeout=timeout,
                check_compatibility=False,
            )
            self._healthy = bool(self._client.collection_exists(self._collection_name))
            if not self._healthy:
                distance = getattr(models.Distance, self._distance, models.Distance.COSINE)
                self._client.create_collection(
                    collection_name=self._collection_name,
                    vectors_config=models.VectorParams(
                        size=self._vector_size,
                        distance=distance,
                    ),
                )
                self._healthy = True
            return self._healthy
        except Exception as exc:
            self._last_connect_error = str(exc)
            logger.debug('Qdrant connect failed: %s', exc)
            self._client = None
            self._healthy = False
            return False

    def _init_client(self) -> None:
        last_err: str | None = None
        for attempt in range(1, _INIT_RETRIES + 1):
            if self._connect_once():
                if attempt > 1:
                    logger.info(
                        'Qdrant vector store connected at %s:%s (attempt %s)',
                        self._host,
                        self._port,
                        attempt,
                    )
                return
            last_err = self._last_connect_error or f'attempt {attempt} failed'
            if attempt < _INIT_RETRIES:
                logger.warning(
                    'Qdrant init attempt %s/%s failed; retry in %.0fs',
                    attempt,
                    _INIT_RETRIES,
                    _INIT_RETRY_DELAY_SEC,
                )
                time.sleep(_INIT_RETRY_DELAY_SEC)

        logger.error(
            'Failed to initialize Qdrant vector store at %s:%s after %s attempts: %s',
            self._host,
            self._port,
            _INIT_RETRIES,
            last_err,
        )

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
            return self._connect_once()
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

    def scroll_all(
        self,
        *,
        limit: int = 256,
        offset: object | None = None,
        with_vectors: bool = False,
    ) -> tuple[list[dict[str, Any]], object | None]:
        if self._client is None:
            return [], None
        try:
            points, next_offset = self._client.scroll(
                collection_name=self._collection_name,
                limit=max(1, int(limit)),
                offset=offset,
                with_payload=True,
                with_vectors=with_vectors,
            )
            out: list[dict[str, Any]] = []
            for point in points:
                item: dict[str, Any] = {
                    'id': str(point.id),
                    'payload': dict(point.payload or {}),
                }
                if with_vectors and point.vector is not None:
                    item['vector'] = point.vector
                out.append(item)
            return out, next_offset
        except Exception:
            logger.exception('Qdrant scroll_all failed')
            return [], None

    def count_by_ship_ids(
        self,
        *,
        ship_ids: list[str],
        page_size: int = 256,
    ) -> dict[str, int]:
        if self._client is None or not ship_ids:
            return {}
        try:
            from qdrant_client import models
        except Exception:
            return {}

        unique = list(dict.fromkeys(str(sid).strip() for sid in ship_ids if str(sid).strip()))
        if not unique:
            return {}

        counts = {sid: 0 for sid in unique}
        offset = None
        try:
            while True:
                points, offset = self._client.scroll(
                    collection_name=self._collection_name,
                    scroll_filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key='ship_id',
                                match=models.MatchAny(any=unique),
                            )
                        ]
                    ),
                    limit=max(1, int(page_size)),
                    offset=offset,
                    with_payload=['ship_id'],
                    with_vectors=False,
                )
                for point in points:
                    ship_id = str((point.payload or {}).get('ship_id') or '').strip()
                    if ship_id in counts:
                        counts[ship_id] += 1
                if offset is None:
                    break
            return counts
        except Exception:
            logger.exception('Qdrant count_by_ship_ids failed')
            return counts

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

    def delete_by_ship_id(self, *, ship_id: str) -> int:
        """Delete all points whose payload ship_id matches. Returns deleted count estimate."""
        if self._client is None:
            return 0
        normalized = str(ship_id or '').strip()
        if not normalized:
            return 0
        try:
            from qdrant_client import models
        except Exception:
            return 0

        points = self.list_by_ship_id(ship_id=normalized, limit=500)
        if not points:
            return 0
        try:
            self._client.delete(
                collection_name=self._collection_name,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key='ship_id',
                                match=models.MatchValue(value=normalized),
                            )
                        ]
                    )
                ),
                wait=True,
            )
            return len(points)
        except Exception:
            logger.exception('Qdrant delete_by_ship_id failed ship_id=%s', normalized)
            return 0
