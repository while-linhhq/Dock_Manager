"""Resolve effective runtime values: port_configs (UI/DB) overrides env defaults.

Keep this module lightweight: it may touch DB/config, but must not import
numpy/torch/cv2/paddle because thread caps call it before AI libraries import.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path

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


def models_dir() -> str:
    """Thư mục gốc chứa model AI (mặc định ``server/models``)."""
    return resolve_port_config('model_dir', settings.MODEL_DIR) or 'models'


def model_file(*parts: str) -> str:
    """Ghép đường dẫn trong thư mục model: ``model_file('dinov2', 'x.engine')``."""
    return os.path.join(models_dir(), *parts)


def _server_root() -> str:
    """Thư mục ``server/`` — dự phòng khi tiến trình chạy từ gốc repo thay vì trong server."""
    return str(Path(__file__).resolve().parents[2])


def find_model_artifact(name: str, extensions: tuple[str, ...]) -> str | None:
    """Tìm file model đầu tiên tồn tại trong thư mục model, theo thứ tự ưu tiên đuôi.

    ``find_model_artifact('dinov2/vit_base_patch14_dinov2', ('.engine', '.safetensors'))``
    """
    roots = [models_dir(), os.path.join(_server_root(), models_dir())]
    for ext in extensions:
        for root in roots:
            candidate = os.path.join(root, f'{name}{ext}')
            if os.path.isfile(candidate):
                return candidate
    return None


def effective_device() -> str:
    return resolve_port_config('device', settings.DEVICE)
