from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.session import get_db
from app.api.deps import get_current_user
from app.schemas.audit_log import AuditLogRead
from app.repositories.audit_log_repository import audit_log_repo

router = APIRouter()


@router.get('/', response_model=List[AuditLogRead])
def list_audit_logs(
    user_id: Optional[int] = None,
    limit: int = 200,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    limit = max(1, min(limit, 1000))
    if user_id:
        return audit_log_repo.get_by_user(db, user_id=user_id, limit=limit)
    return audit_log_repo.get_by_user(db, user_id=None, limit=limit)
