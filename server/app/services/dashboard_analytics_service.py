"""Bốn widget phân tích của dashboard — tổng hợp bằng SQL, không nạp row về Python.

Task 17: trước đây bốn widget (`buildDetectionsByHourLast24h`, `buildTopShipCounts`,
`buildAcceptanceSplit`, `buildConfidenceBuckets` phía client) tự đếm trên 120 row
nhận diện mới nhất mà sidebar tải về. Dashboard phải đạt ngưỡng ≤ 0,30 s nên sidebar
cắt còn 18 row, và bốn widget chuyển sang đọc số tổng hợp từ endpoint này.

Cửa sổ thời gian (quan trọng — hai nhóm khác nhau):

- `by_hour` LUÔN là **24 khung giờ gần nhất** (cửa sổ cố định, đúng như biểu đồ mô
  tả "24 giờ qua"), KHÔNG phụ thuộc `period`. Bucket là giờ UTC đã cắt phút, tăng
  dần, luôn đủ 24 điểm kể cả khi không có row nào.
- `top_ships`, `acceptance`, `confidence_buckets` theo `period` (`day` | `week` |
  `month` | `year`) với **cùng quy ước như `/dashboard/summary`**: biên kỳ tính theo
  Asia/Ho_Chi_Minh rồi quy về UTC, so nửa khoảng `[start, end)` trên `created_at`
  (row đã xoá mềm bị loại).

Mỗi tổng hợp là MỘT truy vấn GROUP BY trong repository (`detection_repository`).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Literal, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.repositories.detection_repository import detection_repo

TZ = ZoneInfo('Asia/Ho_Chi_Minh')

# `year` được thêm ở Task 18: client có nút Ngày/Tháng/Năm (`DashboardPeriod`) và
# `/dashboard/summary` nhận `year`, nên endpoint này phải nhận cùng bộ giá trị —
# thiếu nhánh `year` thì tab "Năm" của dashboard sẽ 422.
Period = Literal['day', 'week', 'month', 'year']

# Số nhãn tàu tối đa của widget "Mã tàu xuất hiện nhiều" (top 8).
TOP_SHIPS_LIMIT = 8


def period_bounds_utc(period: Period) -> Tuple[datetime, datetime]:
    """`(start_utc, end_utc)` của kỳ — biên theo giờ VN, nửa khoảng `[start, end)`.

    Cùng quy ước với `/dashboard/summary`: `day` = ngày dương lịch VN, `month` =
    tháng dương lịch VN, `year` = năm dương lịch VN (01/01 00:00 → 01/01 năm sau,
    đúng khuôn của `/dashboard/summary`). `week` = tuần ISO bắt đầu Thứ Hai 00:00
    giờ VN (dashboard chưa có nút "tuần", nhưng cửa sổ này là phần giao diện của
    endpoint).
    """
    now = datetime.now(TZ)
    if period == 'week':
        start_local = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        end_local = start_local + timedelta(days=7)
    elif period == 'month':
        start_local = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if start_local.month == 12:
            end_local = start_local.replace(year=start_local.year + 1, month=1)
        else:
            end_local = start_local.replace(month=start_local.month + 1)
    elif period == 'year':
        start_local = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end_local = start_local.replace(year=start_local.year + 1)
    else:
        start_local = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_local = start_local + timedelta(days=1)

    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def build_detection_analytics(db: Session, period: Period) -> Dict[str, Any]:
    """Bốn tổng hợp cho `GET /dashboard/detection-analytics` — đúng 4 truy vấn SQL.

    Trả dict thô (endpoint để FastAPI serialize qua response_model
    `DashboardDetectionAnalyticsRead`), đúng hình dạng client cần:
    `by_hour` 24 điểm UTC tăng dần · `top_ships` ≤ 8 nhãn theo count giảm dần ·
    `acceptance` đủ 3 khóa · `confidence_buckets` đủ 3 nhãn theo thứ tự của client.
    """
    start_utc, end_utc = period_bounds_utc(period)

    by_hour = detection_repo.count_by_hour(db)
    top_ships = detection_repo.top_ship_counts(
        db, start=start_utc, end=end_utc, limit=TOP_SHIPS_LIMIT
    )
    acceptance = detection_repo.acceptance_split(db, start=start_utc, end=end_utc)
    confidence_buckets = detection_repo.confidence_bucket_counts(
        db, start=start_utc, end=end_utc
    )

    return {
        'by_hour': [{'hour': hour, 'count': int(count)} for hour, count in by_hour],
        'top_ships': [
            {'label': label, 'count': int(count)} for label, count in top_ships
        ],
        'acceptance': {key: int(value) for key, value in acceptance.items()},
        'confidence_buckets': [
            {'bucket': label, 'count': int(count)} for label, count in confidence_buckets
        ],
    }
