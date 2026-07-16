from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional


class VesselTypeBase(BaseModel):
    type_name: str
    description: Optional[str] = None


class VesselTypeCreate(VesselTypeBase):
    # Danh sách id tàu (tháng) gán cho loại này. None = không đụng membership;
    # [] = gỡ toàn bộ tàu khỏi loại. Áp dụng khi create/update.
    member_vessel_ids: Optional[List[int]] = None


class VesselTypeRead(VesselTypeBase):
    id: int
    created_at: datetime

    model_config = {'from_attributes': True}


class VesselTypeMemberVessel(BaseModel):
    """Tàu (tháng) thuộc một loại — dùng cho picker gán tàu."""

    id: int
    ship_id: str
    name: Optional[str] = None
    classification: str
    vessel_type_id: Optional[int] = None

    model_config = {'from_attributes': True}
