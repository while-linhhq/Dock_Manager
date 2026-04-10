from pydantic import BaseModel
from typing import Optional
from decimal import Decimal


class DashboardStats(BaseModel):
    total_vessels: int
    total_detections_today: int
    pending_orders: int
    completed_orders_today: int
    total_revenue_today: Decimal
    unpaid_invoices: int
    active_cameras: int
