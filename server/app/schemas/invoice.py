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


class InvoiceVesselTypeBrief(BaseModel):
    type_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class InvoiceVesselBrief(BaseModel):
    id: int
    ship_id: str
    vessel_type: Optional[InvoiceVesselTypeBrief] = None

    model_config = ConfigDict(from_attributes=True)


class InvoiceDetectionBrief(BaseModel):
    id: int
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    confidence: Optional[Decimal] = None
    ocr_results: Optional[list[dict]] = None

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
    vessel: Optional[InvoiceVesselBrief] = None
    detection: Optional[InvoiceDetectionBrief] = None
    created_by_label: str = '—'
    vessel_ship_id: Optional[str] = None
    vessel_type_name: Optional[str] = None
    detection_confidence_avg: Optional[Decimal] = None
    berth_duration_hours: Optional[Decimal] = None
    berth_duration_seconds: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode='after')
    def fill_created_by_label(self):
        """Field thường — tránh computed_field (một số client/encoder hiển thị sai)."""
        src = (self.creation_source or 'USER').upper()
        updates: dict = {}
        if self.vessel is not None:
            updates['vessel_ship_id'] = self.vessel.ship_id
            updates['vessel_type_name'] = (
                self.vessel.vessel_type.type_name
                if self.vessel.vessel_type is not None
                else None
            )
        if self.detection is not None:
            start = self.detection.start_time
            end = self.detection.end_time
            if start is not None and end is not None:
                secs = (end - start).total_seconds()
                if secs > 0:
                    updates['berth_duration_seconds'] = int(round(secs))
                    updates['berth_duration_hours'] = (Decimal(str(secs)) / Decimal('3600')).quantize(
                        Decimal('0.0001')
                    )
            ocr = self.detection.ocr_results or []
            confs: list[Decimal] = []
            for item in ocr:
                raw = item.get('conf')
                try:
                    if raw is not None:
                        confs.append(Decimal(str(raw)))
                except Exception:
                    continue
            if confs:
                avg = (sum(confs, Decimal('0')) / Decimal(str(len(confs)))).quantize(Decimal('0.0001'))
                updates['detection_confidence_avg'] = avg
            elif self.detection.confidence is not None:
                try:
                    updates['detection_confidence_avg'] = Decimal(str(self.detection.confidence)).quantize(
                        Decimal('0.0001')
                    )
                except Exception:
                    pass

        if src == 'AI':
            updates['created_by_label'] = 'AI'
            return self.model_copy(update=updates)
        if self.creator is not None:
            c = self.creator
            label = (
                (c.full_name or '').strip()
                or (c.email or '').strip()
                or (c.username or '').strip()
                or str(c.id)
            )
            updates['created_by_label'] = label
            return self.model_copy(update=updates)
        updates['created_by_label'] = '—'
        return self.model_copy(update=updates)
