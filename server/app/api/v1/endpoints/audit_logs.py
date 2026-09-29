from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.session import get_db
from app.api.deps import get_current_user
from app.schemas.audit_log import AuditLogRead
from app.repositories.audit_log_repository import audit_log_repo
from app.utils.pagination import DEFAULT_PAGE_SIZE, resolve_page, set_total_header

router = APIRouter()


@router.get('/', response_model=List[AuditLogRead])
def list_audit_logs(
    response: Response,
    skip: int = 0,
    limit: int = DEFAULT_PAGE_SIZE,
    user_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    user_id = user_id or None
    skip, limit = resolve_page(skip, limit)
    total = audit_log_repo.count_by_user(db, user_id=user_id)
    set_total_header(response, total)
    return audit_log_repo.get_by_user(db, user_id=user_id, limit=limit, skip=skip)
