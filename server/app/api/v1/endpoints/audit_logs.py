from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List, Optional

from app.db.session import get_db
from app.api.deps import get_current_user
from app.schemas.audit_log import AuditLogRead
from app.repositories.audit_log_repository import (
    DEFAULT_ORDER,
    DEFAULT_SORT,
    audit_log_repo,
)
from app.utils.datetimes import as_utc
from app.utils.pagination import DEFAULT_PAGE_SIZE, resolve_page, set_total_header

router = APIRouter()


@router.get('/', response_model=List[AuditLogRead])
def list_audit_logs(
    response: Response,
    skip: int = 0,
    limit: int = DEFAULT_PAGE_SIZE,
    user_id: Optional[int] = None,
    q: Optional[str] = Query(
        None,
        description='Tìm không phân biệt hoa thường: action, record_id, tên / email người dùng',
    ),
    action: Optional[str] = Query(None, description='Lọc chứa trên `action`'),
    table_name: Optional[str] = Query(
        None, description='Lọc chứa trên `entity_type` (nhãn `table_name` của payload)'
    ),
    created_from: Optional[datetime] = Query(
        None, description='Instant UTC (ISO-8601) so với `created_at`'
    ),
    created_to: Optional[datetime] = Query(
        None, description='Instant UTC (ISO-8601) so với `created_at`'
    ),
    sort: str = Query(DEFAULT_SORT, description='created_at | action | table_name'),
    order: str = Query(DEFAULT_ORDER, description='asc | desc'),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Danh sách lịch sử hệ thống — 4 bộ lọc của trang lịch sử chạy ở SQL.

    Port `BackupView.tsx:19-43`: `q` (action, `record_id`, tên/email người dùng),
    `table_name` (nhãn `entity_type` của payload), `action` và `created_from`/
    `created_to` (instant UTC so với `created_at`); `user_id` giữ nguyên như cũ.
    Các bộ lọc này là điều kiện độc lập với nhau và với bộ lọc ẩn READ/HEAD/
    OPTIONS.

    `sort` chỉ nhận `created_at` (mặc định) / `action` / `table_name`; giá trị lạ
    rơi về mặc định, không bao giờ được nội suy vào SQL.
    """
    user_id = user_id or None
    skip, limit = resolve_page(skip, limit)
    filters = {
        'user_id': user_id,
        'q': q,
        'action': action,
        'table_name': table_name,
        'created_from': as_utc(created_from),
        'created_to': as_utc(created_to),
        'sort': sort,
        'order': order,
    }
    set_total_header(response, audit_log_repo.count_by_user(db, **filters))
    return audit_log_repo.get_by_user(db, skip=skip, limit=limit, **filters)
