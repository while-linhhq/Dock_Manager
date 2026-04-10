from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class DetectionMediaBase(BaseModel):
    detection_id: int
    media_type: str  # image | video | thumbnail
    file_path: str
    file_size: Optional[int] = None


class DetectionMediaCreate(DetectionMediaBase):
    pass


class DetectionMediaRead(DetectionMediaBase):
    id: int
    created_at: datetime

    model_config = {'from_attributes': True}
