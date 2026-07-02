"""Small runtime reads from port_configs without importing heavy AI libs.

Used early during process startup (before torch/cv2/paddle imports), so keep this
module lightweight. It may import SQLAlchemy + app settings, but must not import
numpy/torch/cv2/paddle.
"""
from __future__ import annotations

import logging
from functools import lru_cache

from sqlalchemy import create_engine, text

from app.core.config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def load_port_config_map() -> dict[str, str]:
    try:
        engine = create_engine(str(settings.DATABASE_URL), pool_pre_ping=True)
        with engine.connect() as conn:
            rows = conn.execute(text('SELECT key, value FROM port_configs')).fetchall()
        engine.dispose()
        return {str(row[0]): str(row[1]) for row in rows}
    except Exception as err:
        logger.warning('port_config_runtime: failed to load port_configs: %s', err)
        return {}


def get_port_config(key: str, default: str = '') -> str:
    return load_port_config_map().get(key, default)


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


def clear_port_config_cache() -> None:
    load_port_config_map.cache_clear()
