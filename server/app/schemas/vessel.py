from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from datetime import date, datetime
from typing import Literal, Optional
from decimal import Decimal

from app.schemas.fee import normalize_stored_fee_unit

VesselClassificationLiteral = Literal['spot', 'monthly', 'unclassified']


class VesselTypeNested(BaseModel):
    id: int
    type_name: str
    description: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ApplicableFeeRead(BaseModel):
    """First active fee config for the vessel's type (reference pricing)."""

    fee_name: str
    base_fee: Decimal
    unit: Optional[str] = None

    @field_validator('unit', mode='before')
    @classmethod
    def coerce_unit(cls, value: Optional[str]) -> str:
        return normalize_stored_fee_unit(value)

    model_config = ConfigDict(from_attributes=True)


class VesselBase(BaseModel):
    ship_id: str
    name: Optional[str] = None
    # Phân loại cứng của tàu; tab tạo tàu quyết định giá trị.
    classification: VesselClassificationLiteral = 'unclassified'
    vessel_type_id: Optional[int] = None
    owner: Optional[str] = None
    registration_number: Optional[str] = None
    length_m: Optional[Decimal] = None
    registry_expiry: Optional[date] = None
    is_active: bool = True


class VesselCreate(VesselBase):
    @model_validator(mode='after')
    def classification_type_consistency(self):
        if self.classification == 'monthly' and self.vessel_type_id is None:
            raise ValueError('monthly vessel requires vessel_type_id')
        if self.classification != 'monthly':
            object.__setattr__(self, 'vessel_type_id', None)
        return self


class VesselUpdate(BaseModel):
    name: Optional[str] = None
    classification: Optional[VesselClassificationLiteral] = None
    vessel_type_id: Optional[int] = None
    owner: Optional[str] = None
    registration_number: Optional[str] = None
    length_m: Optional[Decimal] = None
    registry_expiry: Optional[date] = None
    is_active: Optional[bool] = None


class VesselRead(VesselBase):
    id: int
    last_seen: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    vessel_type: Optional[VesselTypeNested] = None
    applicable_fee: Optional[ApplicableFeeRead] = None
    visual_reference_count: int = 0

    model_config = ConfigDict(from_attributes=True)
