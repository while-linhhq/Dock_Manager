from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional
from decimal import Decimal


class FeeConfigBase(BaseModel):
    vessel_type_id: Optional[int] = None
    fee_name: str
    base_fee: Decimal
    unit: Optional[str] = None
    is_active: bool = True
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None


class FeeConfigCreate(FeeConfigBase):
    pass


class FeeConfigUpdate(BaseModel):
    fee_name: Optional[str] = None
    base_fee: Optional[Decimal] = None
    unit: Optional[str] = None
    is_active: Optional[bool] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None


class FeeConfigRead(FeeConfigBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {'from_attributes': True}
