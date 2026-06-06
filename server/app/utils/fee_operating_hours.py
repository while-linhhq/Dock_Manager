"""Operating hours parsing/validation for fee_configs (no service imports)."""
from __future__ import annotations

import re
from datetime import datetime, time
from typing import Any, Optional
from zoneinfo import ZoneInfo

VN_TZ = ZoneInfo('Asia/Ho_Chi_Minh')
_WEEKDAY_KEYS = ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')
_TIME_RE = re.compile(r'^([01]?\d|2[0-3]):([0-5]\d)$')


def weekday_key_vn(dt: datetime) -> str:
    if dt.tzinfo is None:
        ref = dt.replace(tzinfo=VN_TZ)
    else:
        ref = dt.astimezone(VN_TZ)
    return _WEEKDAY_KEYS[ref.weekday()]


def parse_hhmm(value: str) -> time:
    match = _TIME_RE.match((value or '').strip())
    if not match:
        raise ValueError(f'invalid time format: {value!r}')
    return time(int(match.group(1)), int(match.group(2)))


def day_schedule_for_weekday(
    operating_hours: Optional[dict[str, Any]],
    weekday: str,
) -> Optional[dict[str, Any]]:
    if not operating_hours or not isinstance(operating_hours, dict):
        return None
    raw = operating_hours.get(weekday)
    if raw is None:
        return None
    if not isinstance(raw, dict):
        return None
    return raw


def operating_hours_has_enforced_day(operating_hours: Optional[dict[str, Any]]) -> bool:
    if not operating_hours or not isinstance(operating_hours, dict):
        return False
    for key in _WEEKDAY_KEYS:
        raw = operating_hours.get(key)
        if not isinstance(raw, dict):
            continue
        if raw.get('closed') is True:
            return True
        if raw.get('open') and raw.get('close'):
            return True
    return False


def is_within_operating_hours(start_vn: datetime, day_schedule: Optional[dict[str, Any]]) -> bool:
    if day_schedule is None:
        return True
    if day_schedule.get('closed') is True:
        return False
    open_raw = day_schedule.get('open')
    close_raw = day_schedule.get('close')
    if not open_raw or not close_raw:
        return True
    open_t = parse_hhmm(str(open_raw))
    close_t = parse_hhmm(str(close_raw))
    t = start_vn.time() if start_vn.tzinfo else start_vn.replace(tzinfo=VN_TZ).time()
    if open_t <= close_t:
        return open_t <= t < close_t
    return t >= open_t or t < close_t


def validate_operating_hours(value: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError('operating_hours must be an object')
    normalized: dict[str, Any] = {}
    weekday_set = frozenset(_WEEKDAY_KEYS)
    for key, raw in value.items():
        if key not in weekday_set:
            continue
        if raw is None:
            normalized[key] = None
            continue
        if not isinstance(raw, dict):
            raise ValueError(f'operating_hours.{key} must be an object or null')
        if raw.get('closed') is True:
            normalized[key] = {'closed': True}
            continue
        open_raw = raw.get('open')
        close_raw = raw.get('close')
        if not open_raw and not close_raw:
            normalized[key] = None
            continue
        if not open_raw or not close_raw:
            raise ValueError(f'operating_hours.{key} requires both open and close')
        parse_hhmm(str(open_raw))
        parse_hhmm(str(close_raw))
        normalized[key] = {'open': str(open_raw).strip(), 'close': str(close_raw).strip()}
    return normalized or None
