from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

FeeBillingUnitLiteral = Literal['per_hour', 'per_month', 'per_year', 'none']

_ALLOWED_UNITS = frozenset({'per_hour', 'per_month', 'per_year', 'none'})


def normalize_stored_fee_unit(value: Optional[str]) -> str:
    if not value or value not in _ALLOWED_UNITS:
        return 'per_month'
    return value


class VesselTypeNestedForFee(BaseModel):
    """Nested type on fee responses (kept here to avoid import cycle with vessel schema)."""

    id: int
    type_name: str
    description: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class FeeConfigBase(BaseModel):
    vessel_type_id: Optional[int] = None
    fee_name: str
    base_fee: Decimal
    unit: Optional[str] = None
    is_active: bool = True
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None


class FeeConfigCreate(FeeConfigBase):
    unit: FeeBillingUnitLiteral = 'per_month'

    @model_validator(mode='after')
    def none_unit_zeroes_fee(self):
        if self.unit == 'none':
            object.__setattr__(self, 'base_fee', Decimal('0'))
        return self


class FeeConfigUpdate(BaseModel):
    fee_name: Optional[str] = None
    base_fee: Optional[Decimal] = None
    unit: Optional[FeeBillingUnitLiteral] = None
    is_active: Optional[bool] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None

    @model_validator(mode='after')
    def none_unit_zeroes_fee(self):
        if self.unit == 'none':
            object.__setattr__(self, 'base_fee', Decimal('0'))
        return self


class FeeConfigRead(FeeConfigBase):
    id: int
    created_at: datetime
    updated_at: datetime
    vessel_type: Optional[VesselTypeNestedForFee] = None

    @field_validator('unit', mode='before')
    @classmethod
    def coerce_unit(cls, value: Optional[str]) -> str:
        return normalize_stored_fee_unit(value)

    model_config = {'from_attributes': True}
