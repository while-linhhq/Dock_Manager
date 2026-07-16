"""Operating hours parsing/validation for fee_configs (no service imports)."""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal
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


def _as_vn(dt: datetime) -> datetime:
    """Đưa về tz Asia/Ho_Chi_Minh (naive coi như đã là giờ VN)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=VN_TZ)
    return dt.astimezone(VN_TZ)


def _instant_is_outside(moment_vn: datetime, operating_hours: Optional[dict[str, Any]]) -> bool:
    """Một thời điểm có nằm NGOÀI khung giờ cho phép không (theo weekday của nó)."""
    weekday = weekday_key_vn(moment_vn)
    day_schedule = day_schedule_for_weekday(
        operating_hours if isinstance(operating_hours, dict) else None, weekday
    )
    if day_schedule is None:
        # Không cấu hình cho ngày này -> không giới hạn -> coi như trong giờ.
        return False
    return not is_within_operating_hours(moment_vn, day_schedule)


def outside_operating_hours_for_interval(
    start: Optional[datetime],
    end: Optional[datetime],
    operating_hours: Optional[dict[str, Any]],
) -> Decimal:
    """Số GIỜ của khoảng [start, end] rơi NGOÀI khung giờ cho phép (chính xác, không làm tròn).

    Cùng ngữ nghĩa với is_within_operating_hours dùng cho phạt phẳng: mỗi thời
    điểm được phân loại theo weekday + giờ-trong-ngày của chính nó, nên hỗ trợ tự
    nhiên khung qua đêm (open>close) và khoảng neo trải nhiều ngày.

    Thuật toán: dồn các mốc ranh giới (nửa đêm mỗi ngày + open/close mỗi ngày)
    rồi với từng đoạn liên tiếp, phân loại theo điểm giữa (predicate hằng trên
    đoạn) và cộng thời lượng nếu ngoài giờ.
    """
    if start is None or end is None:
        return Decimal('0')
    s = _as_vn(start)
    e = _as_vn(end)
    if e <= s:
        return Decimal('0')
    if not operating_hours_has_enforced_day(
        operating_hours if isinstance(operating_hours, dict) else None
    ):
        # Không ép ngày nào -> không giới hạn -> 0 giờ ngoài.
        return Decimal('0')

    boundaries: set[datetime] = {s, e}
    day_cursor: date = s.date()
    last_day: date = e.date()
    while day_cursor <= last_day:
        midnight = datetime.combine(day_cursor, time(0, 0), tzinfo=VN_TZ)
        if s <= midnight <= e:
            boundaries.add(midnight)
        weekday = _WEEKDAY_KEYS[day_cursor.weekday()]
        day_schedule = day_schedule_for_weekday(
            operating_hours if isinstance(operating_hours, dict) else None, weekday
        )
        if isinstance(day_schedule, dict):
            for key in ('open', 'close'):
                raw = day_schedule.get(key)
                if raw:
                    t = parse_hhmm(str(raw))
                    edge = datetime.combine(day_cursor, t, tzinfo=VN_TZ)
                    if s <= edge <= e:
                        boundaries.add(edge)
        day_cursor = day_cursor + timedelta(days=1)

    ordered = sorted(boundaries)
    outside_seconds = Decimal('0')
    for left, right in zip(ordered, ordered[1:]):
        if right <= left:
            continue
        mid = left + (right - left) / 2
        if _instant_is_outside(mid, operating_hours):
            outside_seconds += Decimal(str((right - left).total_seconds()))
    return outside_seconds / Decimal('3600')


def is_interval_outside_operating_hours(
    start: Optional[datetime],
    end: Optional[datetime],
    operating_hours: Optional[dict[str, Any]],
) -> bool:
    """True nếu khoảng neo có BẤT KỲ phần nào rơi ngoài khung giờ cho phép."""
    return outside_operating_hours_for_interval(start, end, operating_hours) > 0


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
