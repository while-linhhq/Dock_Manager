from pydantic import BaseModel, field_validator
from datetime import datetime
from typing import Optional, Any


class CameraBase(BaseModel):
    camera_name: str
    rtsp_url: str
    is_active: bool = True
    location: Optional[str] = None
    description: Optional[str] = None

    @field_validator('is_active', mode='before')
    @classmethod
    def validate_is_active(cls, v: Any) -> bool:
        if v is None:
            return True
        if isinstance(v, str):
            return v.lower() == 'true'
        return bool(v)


class CameraCreate(CameraBase):
    pass


class CameraUpdate(BaseModel):
    camera_name: Optional[str] = None
    rtsp_url: Optional[str] = None
    is_active: Optional[bool] = None
    location: Optional[str] = None
    description: Optional[str] = None


class CameraRead(CameraBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {'from_attributes': True}
