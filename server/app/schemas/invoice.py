from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional, List
from decimal import Decimal


class InvoiceItemCreate(BaseModel):
    fee_config_id: Optional[int] = None
    description: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit_price: Decimal
    amount: Decimal


class InvoiceItemRead(InvoiceItemCreate):
    id: int
    invoice_id: int

    model_config = {'from_attributes': True}


class InvoiceBase(BaseModel):
    invoice_number: str
    order_id: Optional[int] = None
    vessel_id: Optional[int] = None
    detection_id: Optional[int] = None
    subtotal: Optional[Decimal] = None
    tax_amount: Optional[Decimal] = None
    total_amount: Decimal
    payment_status: str = 'UNPAID'
    due_date: Optional[date] = None
    notes: Optional[str] = None


class InvoiceCreate(InvoiceBase):
    created_by: Optional[int] = None
    items: List[InvoiceItemCreate] = []


class InvoiceUpdate(BaseModel):
    invoice_number: Optional[str] = None
    order_id: Optional[int] = None
    vessel_id: Optional[int] = None
    detection_id: Optional[int] = None
    subtotal: Optional[Decimal] = None
    tax_amount: Optional[Decimal] = None
    total_amount: Optional[Decimal] = None
    payment_status: Optional[str] = None
    due_date: Optional[date] = None
    notes: Optional[str] = None


class InvoiceRead(InvoiceBase):
    id: int
    created_by: Optional[int] = None
    paid_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    items: List[InvoiceItemRead] = []

    model_config = {'from_attributes': True}
