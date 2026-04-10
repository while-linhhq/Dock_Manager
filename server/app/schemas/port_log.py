from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Dict, Any


class PortLogBase(BaseModel):
    seq: Optional[int] = None
    logged_at: Optional[datetime] = None
    track_id: Optional[str] = None
    voted_ship_id: Optional[str] = None
    first_seen_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    confidence: Optional[float] = None
    ocr_attempts: Optional[int] = None
    vote_summary: Optional[Dict[str, Any]] = None
    schema_version: int = 3


class PortLogCreate(PortLogBase):
    pass


class PortLogRead(PortLogBase):
    id: int

    model_config = {'from_attributes': True}
