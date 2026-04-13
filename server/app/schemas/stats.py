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
