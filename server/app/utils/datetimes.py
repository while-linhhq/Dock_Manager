"""Chuẩn hoá instant lọc của các endpoint danh sách về UTC."""

from datetime import datetime, timezone
from typing import Optional


def as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Chuẩn hoá instant lọc về UTC; giá trị không kèm offset được hiểu là UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
