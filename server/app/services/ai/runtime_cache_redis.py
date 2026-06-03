from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class RuntimeCacheRedis:
    def __init__(
        self,
        *,
        url: str,
        key_prefix: str = 'dock_manager',
        default_ttl_sec: int = 300,
    ) -> None:
        self._url = str(url).strip()
        self._key_prefix = str(key_prefix or 'dock_manager').strip()
        self._default_ttl = max(1, int(default_ttl_sec))
        self._client = None
        self._healthy = False
        self._connect()

    @property
    def healthy(self) -> bool:
        return self._healthy and self._client is not None

    def _connect(self) -> None:
        try:
            import redis
        except Exception:
            logger.warning('redis package unavailable; runtime cache disabled')
            return
        try:
            self._client = redis.Redis.from_url(self._url, decode_responses=True)
            self._healthy = bool(self._client.ping())
        except Exception:
            logger.exception('Failed to connect Redis runtime cache')
            self._client = None
            self._healthy = False

    def healthcheck(self) -> bool:
        if self._client is None:
            return False
        try:
            self._healthy = bool(self._client.ping())
        except Exception:
            self._healthy = False
        return self._healthy

    def _key(self, raw: str) -> str:
        return f'{self._key_prefix}:{raw}'

    def set_json(self, key: str, value: dict[str, Any], ttl_sec: int | None = None) -> None:
        if self._client is None:
            return
        payload = json.dumps(value, ensure_ascii=True)
        ttl = self._default_ttl if ttl_sec is None else max(1, int(ttl_sec))
        try:
            self._client.setex(self._key(key), ttl, payload)
        except Exception:
            logger.exception('Redis set_json failed for key=%s', key)

    def get_json(self, key: str) -> dict[str, Any] | None:
        if self._client is None:
            return None
        try:
            payload = self._client.get(self._key(key))
            if not payload:
                return None
            loaded = json.loads(payload)
            return loaded if isinstance(loaded, dict) else None
        except Exception:
            logger.exception('Redis get_json failed for key=%s', key)
            return None

    def delete(self, key: str) -> None:
        if self._client is None:
            return
        try:
            self._client.delete(self._key(key))
        except Exception:
            logger.exception('Redis delete failed for key=%s', key)
