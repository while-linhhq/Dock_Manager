from decimal import Decimal
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, computed_field


def normalize_order_status(value: Optional[str]) -> str:
    """Map FE lowercase / processing → DB CHECK constraint values."""
    if value is None or str(value).strip() == '':
        return 'PENDING'
    key = str(value).strip().lower()
    return {
        'pending': 'PENDING',
        'processing': 'PENDING',
        'completed': 'COMPLETED',
        'cancelled': 'CANCELLED',
    }.get(key, 'PENDING')


class OrderBase(BaseModel):
    vessel_id: Optional[int] = None
    order_number: str
    description: Optional[str] = None
    status: str = 'PENDING'
    notes: Optional[str] = None
    total_amount: Optional[Decimal] = None


class OrderCreate(BaseModel):
    """Payload from UI: optional order_number, cargo_details alias for description."""

    order_number: Optional[str] = None
    vessel_id: Optional[int] = None
    description: Optional[str] = None
    cargo_details: Optional[str] = None
    total_amount: Optional[Decimal] = None
    status: str = 'PENDING'
    notes: Optional[str] = None
    created_by: Optional[int] = None


class OrderUpdate(BaseModel):
    vessel_id: Optional[int] = None
    description: Optional[str] = None
    cargo_details: Optional[str] = None
    total_amount: Optional[Decimal] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    updated_by: Optional[int] = None


class OrderStatusUpdate(BaseModel):
    status: str
    updated_by: Optional[int] = None


class VesselOrderBrief(BaseModel):
    """Tàu kèm đơn — đủ cho bảng đơn hàng (tránh lazy-load không có vessel)."""

    id: int
    ship_id: str
    name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class OrderRead(OrderBase):
    id: int
    created_by: Optional[int] = None
    updated_by: Optional[int] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    updated_at: datetime
    vessel: Optional[VesselOrderBrief] = None

    model_config = ConfigDict(from_attributes=True)

    @computed_field
    @property
    def cargo_details(self) -> Optional[str]:
        return self.description
