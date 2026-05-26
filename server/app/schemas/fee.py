from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.utils.fee_billing_unit import normalize_fee_billing_unit

FeeBillingUnitLiteral = Literal['per_hour', 'per_month', 'per_year', 'per_berth_visit', 'none']
BerthLimitUnitLiteral = Literal['day', 'month']

_ALLOWED_BERTH_UNITS = frozenset({'day', 'month'})


def normalize_stored_fee_unit(value: Optional[str]) -> str:
    return normalize_fee_billing_unit(value)


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
    berth_limit_count: Optional[int] = None
    berth_limit_unit: Optional[BerthLimitUnitLiteral] = None


class FeeConfigCreate(FeeConfigBase):
    unit: FeeBillingUnitLiteral = 'per_month'

    @model_validator(mode='after')
    def none_unit_zeroes_fee(self):
        if self.unit == 'none':
            object.__setattr__(self, 'base_fee', Decimal('0'))
        return self

    @model_validator(mode='after')
    def berth_limit_fields_paired(self):
        count = self.berth_limit_count
        unit = self.berth_limit_unit
        if count is None and unit is None:
            return self
        if count is not None and count > 0 and unit in _ALLOWED_BERTH_UNITS:
            return self
        raise ValueError('berth_limit_count must be > 0 when berth_limit_unit is set')


class FeeConfigUpdate(BaseModel):
    fee_name: Optional[str] = None
    base_fee: Optional[Decimal] = None
    unit: Optional[FeeBillingUnitLiteral] = None
    is_active: Optional[bool] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    berth_limit_count: Optional[int] = None
    berth_limit_unit: Optional[BerthLimitUnitLiteral] = None

    @model_validator(mode='after')
    def none_unit_zeroes_fee(self):
        if self.unit == 'none':
            object.__setattr__(self, 'base_fee', Decimal('0'))
        return self

    @model_validator(mode='after')
    def berth_limit_fields_paired(self):
        count = self.berth_limit_count
        unit = self.berth_limit_unit
        if count is None and unit is None:
            return self
        if count is not None and count > 0 and unit in _ALLOWED_BERTH_UNITS:
            return self
        raise ValueError('berth_limit_count must be > 0 when berth_limit_unit is set')


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
