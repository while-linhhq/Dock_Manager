from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class OrderBase(BaseModel):
    vessel_id: Optional[int] = None
    order_number: str
    description: Optional[str] = None
    status: str = 'PENDING'
    notes: Optional[str] = None


class OrderCreate(OrderBase):
    created_by: Optional[int] = None


class OrderUpdate(BaseModel):
    description: Optional[str] = None
    notes: Optional[str] = None
    updated_by: Optional[int] = None


class OrderStatusUpdate(BaseModel):
    status: str  # PENDING | COMPLETED | CANCELLED
    updated_by: Optional[int] = None


class OrderRead(OrderBase):
    id: int
    created_by: Optional[int] = None
    updated_by: Optional[int] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    updated_at: datetime

    model_config = {'from_attributes': True}
