from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from decimal import Decimal


class PaymentBase(BaseModel):
    amount: Decimal
    payment_method: Optional[str] = None
    payment_reference: Optional[str] = None
    notes: Optional[str] = None


class PaymentCreate(PaymentBase):
    invoice_id: int
    created_by: Optional[int] = None


class PaymentRead(PaymentBase):
    id: int
    invoice_id: int
    paid_at: datetime
    created_by: Optional[int] = None
    created_at: datetime

    model_config = {'from_attributes': True}
