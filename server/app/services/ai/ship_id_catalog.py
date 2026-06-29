"""Known ship IDs: Qdrant visual refs and/or registered vessels."""
from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

from app.services.ship_id_utils import is_unknown_ship_id, normalize_ship_id

if TYPE_CHECKING:
    from app.services.ai.vector_store_qdrant import QdrantVectorStore

_log = logging.getLogger(__name__)

_CACHE_TTL_SEC = 120.0


class ShipIdCatalog:
    def __init__(
        self,
        vector_store: QdrantVectorStore | None = None,
        *,
        enabled: bool = True,
    ) -> None:
        self._vector_store = vector_store
        self._enabled = enabled
        self._cache: dict[str, tuple[bool, float]] = {}
        self._lock = threading.RLock()

    def set_vector_store(self, vector_store: QdrantVectorStore | None) -> None:
        self._vector_store = vector_store

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)

    def is_known(self, ship_id: str | None) -> bool:
        # Gating disabled: trust rule-engine output, treat any valid id as known.
        if not self._enabled:
            normalized = normalize_ship_id(ship_id)
            return bool(normalized) and not is_unknown_ship_id(normalized)
        normalized = normalize_ship_id(ship_id)
        if not normalized or is_unknown_ship_id(normalized):
            return False
        now = time.time()
        with self._lock:
            cached = self._cache.get(normalized)
            if cached is not None and now - cached[1] < _CACHE_TTL_SEC:
                return cached[0]
        known = self._lookup(normalized)
        with self._lock:
            self._cache[normalized] = (known, now)
        return known

    def _lookup(self, ship_id: str) -> bool:
        store = self._vector_store
        if store is not None and store.healthy and store.has_ship_id(ship_id=ship_id):
            return True
        try:
            from app.db.session import SessionLocal
            from app.repositories.vessel_repository import vessel_repo

            db = SessionLocal()
            try:
                return vessel_repo.get_by_ship_id_normalized(db, ship_id) is not None
            finally:
                db.close()
        except Exception:
            _log.debug('ShipIdCatalog DB lookup failed ship_id=%s', ship_id, exc_info=True)
            return False
