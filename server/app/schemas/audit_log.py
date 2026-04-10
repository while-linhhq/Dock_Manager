from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Any


class AuditLogRead(BaseModel):
    id: int
    user_id: Optional[int] = None
    action: str
    entity_type: str
    entity_id: Optional[int] = None
    details: Optional[dict[str, Any]] = None
    ip_address: Optional[str] = None
    created_at: datetime

    model_config = {'from_attributes': True}
