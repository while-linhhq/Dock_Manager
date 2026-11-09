"""Helper dùng chung cho bộ lọc SQL.

`escape_like` là chỗ duy nhất định nghĩa việc escape wildcard của LIKE/ILIKE:
người dùng gõ `%` hay `_` phải được hiểu là ký tự thường, không phải "khớp tất cả".
"""
from typing import Any

LIKE_ESCAPE: str = '\\'


def escape_like(value: str) -> str:
    """Escape wildcard của LIKE/ILIKE để `q` chỉ khớp đúng ký tự người dùng gõ."""
    return value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


def contains_pattern(value: str) -> str:
    """Mẫu `%value%` cho ILIKE, wildcard bên trong `value` đã bị escape."""
    return f'%{escape_like(value)}%'


def ilike_contains(column: Any, value: str):
    """Biểu thức `column ILIKE '%value%'` an toàn với wildcard trong `value`."""
    return column.ilike(contains_pattern(value), escape=LIKE_ESCAPE)
