"""Resolve effective runtime values: port_configs (UI/DB) overrides env defaults.

Keep this module lightweight: it may touch DB/config, but must not import
numpy/torch/cv2/paddle because thread caps call it before AI libraries import.
"""
from __future__ import annotations

import logging
from functools import lru_cache

from app.core.config import settings
from app.db.session import SessionLocal
from app.repositories.port_config_repository import port_config_repo

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def load_port_config_map() -> dict[str, str]:
    db = SessionLocal()
    try:
        return {row.key: str(row.value or '').strip() for row in port_config_repo.get_all(db)}
    except Exception as exc:
        logger.warning('port_configs unavailable: %s', exc)
        return {}
    finally:
        db.close()


def clear_port_config_cache() -> None:
    load_port_config_map.cache_clear()


def get_port_config(key: str, default: str = '') -> str:
    return load_port_config_map().get(key, default)


def resolve_port_config(key: str, default: str) -> str:
    value = get_port_config(key)
    return str(value).strip() if value else str(default).strip()


def get_port_bool(key: str, default: bool) -> bool:
    raw = get_port_config(key, '').strip().lower()
    if raw in ('1', 'true', 'yes', 'on'):
        return True
    if raw in ('0', 'false', 'no', 'off'):
        return False
    return default


def get_port_int(key: str, default: int) -> int:
    raw = get_port_config(key, '').strip()
    if not raw:
        return default
    try:
        value = int(raw)
        return value if value > 0 else default
    except ValueError:
        return default


def get_port_float(key: str, default: float) -> float:
    raw = get_port_config(key, '').strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def effective_model_path() -> str:
    return resolve_port_config('model_path', settings.MODEL_PATH)


def effective_device() -> str:
    return resolve_port_config('device', settings.DEVICE)
