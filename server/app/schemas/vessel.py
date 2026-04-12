from pydantic import BaseModel, ConfigDict, field_validator
from datetime import datetime
from typing import Optional
from decimal import Decimal

from app.schemas.fee import normalize_stored_fee_unit


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
    vessel_type_id: Optional[int] = None
    owner: Optional[str] = None
    registration_number: Optional[str] = None
    is_active: bool = True


class VesselCreate(VesselBase):
    pass


class VesselUpdate(BaseModel):
    name: Optional[str] = None
    vessel_type_id: Optional[int] = None
    owner: Optional[str] = None
    registration_number: Optional[str] = None
    is_active: Optional[bool] = None


class VesselRead(VesselBase):
    id: int
    last_seen: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    vessel_type: Optional[VesselTypeNested] = None
    applicable_fee: Optional[ApplicableFeeRead] = None

    model_config = ConfigDict(from_attributes=True)
