"""Resolve effective runtime values: port_configs (UI/DB) overrides env defaults."""
from __future__ import annotations

import logging

from app.core.config import settings
from app.db.session import SessionLocal
from app.repositories.port_config_repository import port_config_repo

logger = logging.getLogger(__name__)


def load_port_config_map() -> dict[str, str]:
    db = SessionLocal()
    try:
        return {row.key: str(row.value or '').strip() for row in port_config_repo.get_all(db)}
    except Exception as exc:
        logger.warning('port_configs unavailable: %s', exc)
        return {}
    finally:
        db.close()


def resolve_port_config(key: str, default: str) -> str:
    value = load_port_config_map().get(key)
    return str(value).strip() if value else str(default).strip()


def effective_model_path() -> str:
    return resolve_port_config('model_path', settings.MODEL_PATH)


def effective_device() -> str:
    return resolve_port_config('device', settings.DEVICE)
