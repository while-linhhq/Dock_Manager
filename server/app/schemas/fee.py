from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.utils.fee_billing_unit import normalize_fee_billing_unit
from app.utils.fee_operating_hours import operating_hours_has_enforced_day, validate_operating_hours

FeeBillingUnitLiteral = Literal['per_hour', 'per_month', 'per_year', 'per_berth_visit', 'none']
BerthLimitUnitLiteral = Literal['day', 'month']
WeekdayKeyLiteral = Literal['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']

_ALLOWED_BERTH_UNITS = frozenset({'day', 'month'})


def _validate_fee_scope(*, vessel_id: Optional[int], vessel_type_id: Optional[int]) -> None:
    has_vessel = vessel_id is not None
    has_type = vessel_type_id is not None
    if has_vessel == has_type:
        raise ValueError(
            'fee_config phải có chính xác một phạm vi: vessel_id (tàu lẻ) '
            'hoặc vessel_type_id (tàu tháng)',
        )


def normalize_stored_fee_unit(value: Optional[str]) -> str:
    return normalize_fee_billing_unit(value)


def _validate_penalty_fields(
    *,
    berth_limit_count: Optional[int],
    berth_limit_unit: Optional[str],
    over_limit_penalty_amount: Optional[Decimal],
    outside_hours_penalty_amount: Optional[Decimal],
    operating_hours: Optional[dict[str, Any]],
    max_berth_duration_minutes: Optional[int] = None,
    over_duration_penalty_amount: Optional[Decimal] = None,
    outside_hours_penalty_per_hour: Optional[Decimal] = None,
) -> None:
    over_penalty = Decimal(str(over_limit_penalty_amount or 0))
    if over_penalty > 0:
        if not (
            berth_limit_count is not None
            and berth_limit_count > 0
            and berth_limit_unit in _ALLOWED_BERTH_UNITS
        ):
            raise ValueError(
                'over_limit_penalty_amount requires berth_limit_count and berth_limit_unit',
            )

    outside_penalty = Decimal(str(outside_hours_penalty_amount or 0))
    if outside_penalty > 0 and not operating_hours_has_enforced_day(operating_hours):
        raise ValueError(
            'outside_hours_penalty_amount requires operating_hours for at least one weekday',
        )

    outside_per_hour = Decimal(str(outside_hours_penalty_per_hour or 0))
    if outside_per_hour > 0 and not operating_hours_has_enforced_day(operating_hours):
        raise ValueError(
            'outside_hours_penalty_per_hour requires operating_hours for at least one weekday',
        )

    over_duration_penalty = Decimal(str(over_duration_penalty_amount or 0))
    if over_duration_penalty > 0 and not (
        max_berth_duration_minutes is not None and max_berth_duration_minutes > 0
    ):
        raise ValueError(
            'over_duration_penalty_amount requires max_berth_duration_minutes > 0',
        )


class VesselTypeNestedForFee(BaseModel):
    """Nested type on fee responses (kept here to avoid import cycle with vessel schema)."""

    id: int
    type_name: str
    description: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class VesselNestedForFee(BaseModel):
    """Nested vessel on fee responses (fee giờ gắn theo mã tàu)."""

    id: int
    ship_id: str
    name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class FeeConfigBase(BaseModel):
    vessel_type_id: Optional[int] = None
    vessel_id: Optional[int] = None
    fee_name: str
    base_fee: Decimal
    unit: Optional[str] = None
    is_active: bool = True
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    berth_limit_count: Optional[int] = None
    berth_limit_unit: Optional[BerthLimitUnitLiteral] = None
    over_limit_penalty_amount: Optional[Decimal] = None
    outside_hours_penalty_amount: Optional[Decimal] = None
    outside_hours_penalty_per_hour: Optional[Decimal] = None
    max_berth_duration_minutes: Optional[int] = None
    over_duration_penalty_amount: Optional[Decimal] = None
    operating_hours: Optional[dict[str, Any]] = None

    @field_validator('operating_hours', mode='before')
    @classmethod
    def validate_operating_hours(cls, value: Any) -> Optional[dict[str, Any]]:
        return validate_operating_hours(value)


class FeeConfigCreate(FeeConfigBase):
    unit: FeeBillingUnitLiteral = 'per_month'

    @model_validator(mode='after')
    def exactly_one_scope(self):
        _validate_fee_scope(vessel_id=self.vessel_id, vessel_type_id=self.vessel_type_id)
        return self

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

    @model_validator(mode='after')
    def berth_duration_fields_paired(self):
        minutes = self.max_berth_duration_minutes
        if minutes is not None and minutes <= 0:
            raise ValueError('max_berth_duration_minutes must be > 0 when set')
        return self

    @model_validator(mode='after')
    def penalty_fields_consistent(self):
        _validate_penalty_fields(
            berth_limit_count=self.berth_limit_count,
            berth_limit_unit=self.berth_limit_unit,
            over_limit_penalty_amount=self.over_limit_penalty_amount,
            outside_hours_penalty_amount=self.outside_hours_penalty_amount,
            operating_hours=self.operating_hours,
            max_berth_duration_minutes=self.max_berth_duration_minutes,
            over_duration_penalty_amount=self.over_duration_penalty_amount,
            outside_hours_penalty_per_hour=self.outside_hours_penalty_per_hour,
        )
        return self


class FeeConfigUpdate(BaseModel):
    vessel_id: Optional[int] = None
    vessel_type_id: Optional[int] = None
    fee_name: Optional[str] = None
    base_fee: Optional[Decimal] = None
    unit: Optional[FeeBillingUnitLiteral] = None
    is_active: Optional[bool] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    berth_limit_count: Optional[int] = None
    berth_limit_unit: Optional[BerthLimitUnitLiteral] = None
    over_limit_penalty_amount: Optional[Decimal] = None
    outside_hours_penalty_amount: Optional[Decimal] = None
    outside_hours_penalty_per_hour: Optional[Decimal] = None
    max_berth_duration_minutes: Optional[int] = None
    over_duration_penalty_amount: Optional[Decimal] = None
    operating_hours: Optional[dict[str, Any]] = None

    @field_validator('operating_hours', mode='before')
    @classmethod
    def validate_operating_hours(cls, value: Any) -> Optional[dict[str, Any]]:
        return validate_operating_hours(value)

    @model_validator(mode='after')
    def none_unit_zeroes_fee(self):
        if self.unit == 'none':
            object.__setattr__(self, 'base_fee', Decimal('0'))
        return self

    @model_validator(mode='after')
    def berth_duration_fields_paired(self):
        minutes = self.max_berth_duration_minutes
        if minutes is not None and minutes <= 0:
            raise ValueError('max_berth_duration_minutes must be > 0 when set')
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
    vessel: Optional[VesselNestedForFee] = None

    @field_validator('unit', mode='before')
    @classmethod
    def coerce_unit(cls, value: Optional[str]) -> str:
        return normalize_stored_fee_unit(value)

    model_config = {'from_attributes': True}
