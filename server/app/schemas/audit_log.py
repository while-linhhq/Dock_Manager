from pydantic import BaseModel, model_validator
from datetime import datetime
from typing import Optional, Any


class AuditLogUserBrief(BaseModel):
    id: int
    username: str
    full_name: Optional[str] = None
    email: Optional[str] = None

    model_config = {'from_attributes': True}


class AuditLogRead(BaseModel):
    id: int
    user_id: Optional[int] = None
    action: str
    entity_type: str
    entity_id: Optional[int] = None
    details: Optional[dict[str, Any]] = None
    ip_address: Optional[str] = None
    created_at: datetime
    user: Optional[AuditLogUserBrief] = None
    table_name: str = 'system'
    record_id: str = '—'

    model_config = {'from_attributes': True}

    @model_validator(mode='after')
    def fill_legacy_aliases(self):
        table_name = (self.entity_type or 'system').strip() or 'system'
        record_id = str(self.entity_id) if self.entity_id is not None else '—'
        return self.model_copy(update={'table_name': table_name, 'record_id': record_id})
