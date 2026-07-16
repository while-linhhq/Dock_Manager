"""Thống kê số LƯỢT neo đậu NGOÀI khung giờ cho phép, gộp theo (mã tàu, ngày VN).

Áp cho MỌI tàu (lẻ + tháng) — thuần đếm/giám sát. Một lượt neo (detection) được
tính là 'ngoài giờ' nếu khoảng neo (berth-in → berth-out, fallback start→end) có
BẤT KỲ phần nào rơi ngoài operating_hours của một fee áp dụng cho tàu đó.

Phí phạt theo giờ (chỉ tàu tháng) được tính riêng ở fee_penalty_service; module
này chỉ đếm, không tính tiền.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.detection import Detection
from app.models.vessel import Vessel
from app.services.fee_resolution_service import resolve_billable_fees
from app.services.ship_id_utils import is_unknown_ship_id
from app.utils.fee_operating_hours import is_interval_outside_operating_hours

VN_TZ = ZoneInfo('Asia/Ho_Chi_Minh')
UTC = ZoneInfo('UTC')


def _vn_date(dt: Optional[datetime]) -> Optional[date]:
    if dt is None:
        return None
    # PostgreSQL driver may return DB timestamps without tzinfo; project stores
    # those values as UTC, not Vietnam wall-clock time.
    ref = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt
    return ref.astimezone(VN_TZ).date()


def outside_hours_berth_summary(
    db: Session,
    *,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    ship_id: Optional[str] = None,
) -> list[dict]:
    """Trả [{ship_id, date: 'YYYY-MM-DD', count}], mỗi phần tử = số lượt neo ngoài giờ.

    date_from/date_to lọc theo ngày VN của mốc bắt đầu neo (bao gồm cả 2 đầu).
    ship_id (tùy chọn) lọc đúng một mã tàu (không phân biệt hoa/thường, trim).
    """
    time_col = func.coalesce(Detection.berth_in_time, Detection.start_time, Detection.created_at)

    q = (
        db.query(Detection, Vessel)
        .join(Vessel, Detection.vessel_id == Vessel.id)
        .filter(Detection.deleted_at.is_(None))
    )

    if ship_id:
        normalized = ship_id.strip().upper()
        q = q.filter(func.upper(func.trim(Vessel.ship_id)) == normalized)

    # Lọc thô theo cửa sổ UTC nới rộng ±1 ngày để không cắt nhầm quanh ranh giới TZ;
    # lọc ngày VN chính xác lại ở Python bên dưới.
    if date_from is not None:
        start_utc = datetime.combine(date_from, datetime.min.time(), tzinfo=VN_TZ).astimezone(UTC)
        q = q.filter(time_col >= start_utc - timedelta(days=1))
    if date_to is not None:
        end_utc = datetime.combine(
            date_to + timedelta(days=1), datetime.min.time(), tzinfo=VN_TZ
        ).astimezone(UTC)
        q = q.filter(time_col < end_utc + timedelta(days=1))

    # Cache operating_hours theo vessel_id (nhiều detection cùng tàu).
    fees_hours_cache: dict[int, list[dict]] = {}

    counts: dict[tuple[str, date], int] = defaultdict(int)

    for det, vessel in q.all():
        sid = (vessel.ship_id or '').strip()
        if not sid or is_unknown_ship_id(sid):
            continue
        ref = det.berth_in_time or det.start_time or det.created_at
        vn_d = _vn_date(ref)
        if vn_d is None:
            continue
        if date_from is not None and vn_d < date_from:
            continue
        if date_to is not None and vn_d > date_to:
            continue

        if vessel.id not in fees_hours_cache:
            fees = resolve_billable_fees(db, vessel)
            fees_hours_cache[vessel.id] = [
                fee.operating_hours
                for fee in fees
                if isinstance(fee.operating_hours, dict)
            ]
        hours_list = fees_hours_cache[vessel.id]
        if not hours_list:
            continue

        start = det.berth_in_time or det.start_time
        end = det.berth_out_time or det.end_time
        is_outside = any(
            is_interval_outside_operating_hours(start, end, hours) for hours in hours_list
        )
        if is_outside:
            counts[(sid, vn_d)] += 1

    return [
        {'ship_id': sid, 'date': d.isoformat(), 'count': c}
        for (sid, d), c in sorted(counts.items(), key=lambda kv: (kv[0][1], kv[0][0]), reverse=True)
    ]
