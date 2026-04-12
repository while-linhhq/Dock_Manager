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
