from pydantic import BaseModel, ConfigDict, model_validator
from datetime import date, datetime
from typing import Optional, List
from decimal import Decimal


class InvoiceItemCreate(BaseModel):
    fee_config_id: Optional[int] = None
    description: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit_price: Decimal
    amount: Optional[Decimal] = None

    @model_validator(mode='after')
    def derive_amount(self):
        if self.amount is not None:
            return self
        q = self.quantity if self.quantity is not None else Decimal('1')
        amt = (q * self.unit_price).quantize(Decimal('0.01'))
        return self.model_copy(update={'amount': amt, 'quantity': q})


class FeeConfigOnLineItem(BaseModel):
    fee_name: str
    unit: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class InvoiceItemRead(BaseModel):
    id: int
    invoice_id: int
    fee_config_id: Optional[int] = None
    description: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit_price: Decimal
    amount: Decimal
    fee_config: Optional[FeeConfigOnLineItem] = None

    model_config = ConfigDict(from_attributes=True)


class InvoiceCreatorBrief(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


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
    creation_source: str = 'USER'


class InvoiceCreate(BaseModel):
    invoice_number: Optional[str] = None
    order_id: Optional[int] = None
    vessel_id: Optional[int] = None
    detection_id: Optional[int] = None
    subtotal: Optional[Decimal] = None
    tax_amount: Optional[Decimal] = None
    total_amount: Optional[Decimal] = None
    payment_status: str = 'UNPAID'
    due_date: Optional[date] = None
    notes: Optional[str] = None
    creation_source: str = 'USER'
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
    creator: Optional[InvoiceCreatorBrief] = None
    paid_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    items: List[InvoiceItemRead] = []
    created_by_label: str = '—'

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode='after')
    def fill_created_by_label(self):
        """Field thường — tránh computed_field (một số client/encoder hiển thị sai)."""
        src = (self.creation_source or 'USER').upper()
        if src == 'AI':
            return self.model_copy(update={'created_by_label': 'AI'})
        if self.creator is not None:
            c = self.creator
            label = (
                (c.full_name or '').strip()
                or (c.email or '').strip()
                or (c.username or '').strip()
                or str(c.id)
            )
            return self.model_copy(update={'created_by_label': label})
        return self.model_copy(update={'created_by_label': '—'})
