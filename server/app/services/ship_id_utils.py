"""Shared ship_id normalization helpers (no service-layer imports)."""
from __future__ import annotations

from typing import Optional

_UNKNOWN_SHIP = frozenset({'', 'UNKNOWN', 'KHÔNG XÁC ĐỊNH', 'N/A'})


def normalize_ship_id(ship_id: Optional[str]) -> str:
    return (ship_id or '').strip().upper()


def is_unknown_ship_id(ship_id: Optional[str]) -> bool:
    return normalize_ship_id(ship_id) in _UNKNOWN_SHIP
