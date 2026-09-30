from datetime import datetime
from decimal import Decimal
from typing import List, Literal

from pydantic import BaseModel


class DashboardStats(BaseModel):
    total_vessels: int
    total_detections_today: int
    pending_orders: int
    completed_orders_today: int
    total_revenue_today: Decimal
    unpaid_invoices: int
    active_cameras: int


class DashboardSummaryRead(BaseModel):
    period: Literal['day', 'month', 'year']
    period_start: datetime
    period_end: datetime
    distinct_ships_detected: int
    transient_fee_revenue: Decimal
    auto_invoices_created: int
    pending_orders: int
    revenue_chart_labels: List[str]
    revenue_chart_totals: List[float]
    revenue_chart_ai: List[float]
    revenue_chart_manual: List[float]
    top_ship_labels: List[str]
    top_ship_counts: List[int]
    detections_review_accepted: int
    detections_review_not_accepted: int
    detections_review_unassigned: int
    detection_volume_labels: List[str]
    detection_volume_counts: List[int]
    boundary_in_total: int
    boundary_out_total: int
    boundary_volume_labels: List[str]
    boundary_in_counts: List[int]
    boundary_out_counts: List[int]


class DashboardSystemOverviewRead(BaseModel):
    registered_vessels_day: int
    registered_vessels_month: int
    registered_vessels_year: int
    total_registered_vessels: int
    vessels_without_type: int
    vessels_no_fee: int
    vessels_billable: int
    total_vessel_types: int
    vessel_types_without_active_fee: int
    active_cameras: int
    inactive_cameras: int
    pending_orders: int
    unpaid_invoices: int
    ai_invoices: int


class DetectionAnalyticsHourRead(BaseModel):
    """Một khung giờ của biểu đồ "24 giờ qua" — `hour` là ISO-8601 UTC."""

    hour: datetime
    count: int


class DetectionAnalyticsShipRead(BaseModel):
    """Một nhãn tàu (`getDetectionShipLabel` của client) và số lượt trong kỳ."""

    label: str
    count: int


class DetectionAnalyticsBucketRead(BaseModel):
    """Một bucket độ tin cậy — nhãn trùng `buildConfidenceBuckets` của client."""

    bucket: str
    count: int


class DetectionAnalyticsAcceptanceRead(BaseModel):
    """Trạng thái duyệt: accepted = TRUE, rejected = FALSE, pending = NULL.

    Client gắn nhãn cho ba khóa này theo đúng thứ tự
    `['Đã xác nhận', 'Chưa xác nhận', 'Chưa gán']`.
    """

    accepted: int
    rejected: int
    pending: int


class DashboardDetectionAnalyticsRead(BaseModel):
    """`GET /dashboard/detection-analytics` — bốn widget phân tích của dashboard.

    - `by_hour`: luôn đủ 24 khung giờ gần nhất, tăng dần theo UTC (cửa sổ cố định,
      không phụ thuộc `period`).
    - `top_ships`: tối đa 8 nhãn, sắp theo `count` giảm dần.
    - `acceptance`: đủ ba khóa, nhóm vắng mặt = 0.
    - `confidence_buckets`: đủ ba nhãn `'< 50%'`, `'50–75%'`, `'≥ 75%'` theo thứ tự,
      bucket vắng mặt = 0.
    """

    by_hour: List[DetectionAnalyticsHourRead]
    top_ships: List[DetectionAnalyticsShipRead]
    acceptance: DetectionAnalyticsAcceptanceRead
    confidence_buckets: List[DetectionAnalyticsBucketRead]
