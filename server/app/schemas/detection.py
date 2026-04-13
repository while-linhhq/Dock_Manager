from pydantic import BaseModel, model_validator
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
    audit_image_url: Optional[str] = None
    video_url: Optional[str] = None

    model_config = {'from_attributes': True}

    @model_validator(mode='after')
    def fill_audit_image_url(self):
        path = (self.audit_image_path or '').strip()
        updates: dict[str, Optional[str]] = {}

        if path:
            normalized = path.replace('\\', '/')
            if normalized.startswith('http://') or normalized.startswith('https://'):
                updates['audit_image_url'] = normalized
            else:
                normalized = normalized.lstrip('./')
                updates['audit_image_url'] = f'/{normalized}' if normalized.startswith('runs/') else None
        else:
            updates['audit_image_url'] = None

        vpath = (self.video_path or '').strip()
        if vpath:
            vnormalized = vpath.replace('\\', '/')
            if vnormalized.startswith('http://') or vnormalized.startswith('https://'):
                updates['video_url'] = vnormalized
            else:
                vnormalized = vnormalized.lstrip('./')
                updates['video_url'] = f'/{vnormalized}' if vnormalized.startswith('runs/') else None
        else:
            updates['video_url'] = None

        return self.model_copy(update=updates)
