from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Any


class ExportLogRead(BaseModel):
    id: int
    user_id: Optional[int] = None
    export_type: str
    file_path: Optional[str] = None
    filters: Optional[dict[str, Any]] = None
    row_count: Optional[int] = None
    created_at: datetime

    model_config = {'from_attributes': True}
