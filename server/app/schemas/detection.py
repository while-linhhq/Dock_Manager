from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List, Dict, Any

from app.schemas.vessel import VesselRead


class DetectionBase(BaseModel):
    track_id: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    video_path: Optional[str] = None
    audit_image_path: Optional[str] = None
    ocr_results: Optional[List[Dict[str, Any]]] = None
    confidence: Optional[float] = None
    is_accepted: Optional[bool] = None


class DetectionCreate(DetectionBase):
    vessel_id: Optional[int] = None


class DetectionVerify(BaseModel):
    is_accepted: bool
    rejection_reason: Optional[str] = None


class DetectionRead(DetectionBase):
    id: int
    vessel_id: Optional[int] = None
    vessel: Optional[VesselRead] = None
    verified_by: Optional[int] = None
    verified_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    created_at: datetime

    model_config = {'from_attributes': True}
