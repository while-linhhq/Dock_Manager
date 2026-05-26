from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional
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


class BulkPaymentCreate(BaseModel):
    invoice_ids: List[int] = Field(..., min_length=1)
    payment_method: str = 'cash'
    notes: Optional[str] = None


class BulkPaymentRead(BaseModel):
    invoice_count: int
    total_amount: Decimal
    payments: List[PaymentRead] = []


class BulkSepaySessionCreate(BaseModel):
    invoice_ids: List[int] = Field(..., min_length=1)


class BulkSepaySessionRead(BaseModel):
    reference_code: str
    invoice_count: int
    total_amount: Decimal
    status: str
    invoice_ids: List[int] = []
