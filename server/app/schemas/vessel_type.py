from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class VesselTypeBase(BaseModel):
    type_name: str
    description: Optional[str] = None


class VesselTypeCreate(VesselTypeBase):
    pass


class VesselTypeRead(VesselTypeBase):
    id: int
    created_at: datetime

    model_config = {'from_attributes': True}
