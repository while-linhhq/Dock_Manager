from pydantic import BaseModel, field_validator, model_validator
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


class BoundaryPoint(BaseModel):
    x: float
    y: float


class BoundarySegment(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float


class BoundaryLines(BaseModel):
    enabled: bool = True
    frame_w: int
    frame_h: int
    line1: list[BoundaryPoint]
    line2: list[BoundaryPoint]

    @field_validator('frame_w', 'frame_h', mode='before')
    @classmethod
    def coerce_frame_dims(cls, value: Any) -> Any:
        if isinstance(value, float):
            return round(value)
        return value

    @model_validator(mode='before')
    @classmethod
    def normalize_legacy_segments(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        for key in ('line1', 'line2'):
            line = data.get(key)
            if isinstance(line, dict) and 'x1' in line:
                data[key] = [
                    {'x': line['x1'], 'y': line['y1']},
                    {'x': line['x2'], 'y': line['y2']},
                ]
        return data


class CameraCreate(CameraBase):
    pass


class CameraUpdate(BaseModel):
    camera_name: Optional[str] = None
    rtsp_url: Optional[str] = None
    is_active: Optional[bool] = None
    location: Optional[str] = None
    description: Optional[str] = None
    boundary_lines: Optional[BoundaryLines] = None


class CameraRead(CameraBase):
    id: int
    boundary_lines: Optional[BoundaryLines] = None
    created_at: datetime
    updated_at: datetime

    model_config = {'from_attributes': True}

    @field_validator('boundary_lines', mode='before')
    @classmethod
    def coerce_boundary_lines(cls, value: Any) -> Any:
        if value is None or isinstance(value, BoundaryLines):
            return value
        if isinstance(value, dict):
            return value
        return None
