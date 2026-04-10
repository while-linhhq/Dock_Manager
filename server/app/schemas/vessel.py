from pydantic import BaseModel
from datetime import datetime
from typing import Optional


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

    model_config = {'from_attributes': True}
