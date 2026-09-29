from datetime import date, datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.session import get_db
from app.api.deps import get_current_user
from app.schemas.port_log import PortLogCreate, PortLogRead
from app.repositories.port_log_repository import port_log_repo
from app.services.outside_hours_stats_service import outside_hours_berth_summary
from app.utils.pagination import DEFAULT_PAGE_SIZE, resolve_page, set_total_header

router = APIRouter()


@router.get('/outside-hours-summary')
def outside_hours_summary(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    ship_id: Optional[str] = None,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Số LƯỢT neo ngoài khung giờ cho phép, gộp theo (mã tàu, ngày VN).

    Áp cho mọi tàu (lẻ + tháng), thuần đếm/giám sát — không tính tiền.
    """
    return outside_hours_berth_summary(
        db,
        date_from=date_from,
        date_to=date_to,
        ship_id=ship_id,
    )


@router.post('/', response_model=PortLogRead, status_code=201)
def create_port_log(
    data: PortLogCreate,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    payload = data.model_dump(exclude_unset=True)
    now = datetime.now(timezone.utc)
    if not payload.get('track_id'):
        payload['track_id'] = f'mcp_{uuid4().hex}'
    payload.setdefault('seq', 0)
    payload.setdefault('voted_ship_id', 'UNKNOWN')
    payload.setdefault('logged_at', now)
    payload.setdefault('first_seen_at', now)
    payload.setdefault('last_seen_at', now)
    payload.setdefault('confidence', 0.0)
    payload.setdefault('ocr_attempts', 0)
    payload.setdefault('vote_summary', {})
    payload.setdefault('schema_version', 3)
    return port_log_repo.create(db, payload)


@router.get('/', response_model=List[PortLogRead])
def list_port_logs(
    response: Response,
    skip: int = 0,
    limit: int = DEFAULT_PAGE_SIZE,
    ship_id: Optional[str] = None,
    log_date: Optional[date] = None,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    skip, limit = resolve_page(skip, limit)
    set_total_header(response, port_log_repo.count_logs(db, ship_id=ship_id, log_date=log_date))
    return port_log_repo.get_all_logs(db, skip=skip, limit=limit, ship_id=ship_id, log_date=log_date)


@router.get('/{log_id}', response_model=PortLogRead)
def get_port_log(log_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    obj = port_log_repo.get(db, log_id)
    if not obj:
        raise HTTPException(status_code=404, detail='Port log not found')
    return obj


@router.delete('/{log_id}', status_code=204)
def delete_port_log(log_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    if not port_log_repo.delete(db, log_id):
        raise HTTPException(status_code=404, detail='Port log not found')
