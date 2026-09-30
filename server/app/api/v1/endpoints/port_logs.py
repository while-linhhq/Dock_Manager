from datetime import date, datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.session import get_db
from app.api.deps import get_current_user
from app.schemas.port_log import PortLogCreate, PortLogRead
from app.repositories.port_log_repository import DEFAULT_ORDER, DEFAULT_SORT, port_log_repo
from app.services.outside_hours_stats_service import outside_hours_berth_summary
from app.utils.datetimes import as_utc
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
    ship_id: Optional[str] = Query(None, description='Khớp đúng mã tàu (`voted_ship_id`)'),
    log_date: Optional[date] = Query(None, description='Một ngày lịch của `logged_at`'),
    q: Optional[str] = Query(
        None,
        description='Ô "Track ID (chứa)" của trang: tìm không phân biệt hoa thường trong `track_id`',
    ),
    vessel_type_id: Optional[int] = Query(
        None, description='Loại tàu, tra qua `vessels.ship_id` = `voted_ship_id`'
    ),
    min_confidence: Optional[float] = Query(
        None, description='Độ tin cậy tối thiểu (0..1); thiếu confidence coi là 0'
    ),
    logged_from: Optional[datetime] = Query(
        None, description='Instant UTC (ISO-8601) so với `logged_at`'
    ),
    logged_to: Optional[datetime] = Query(
        None, description='Instant UTC (ISO-8601) so với `logged_at`'
    ),
    sort: str = Query(DEFAULT_SORT, description='time | voted_ship_id'),
    order: str = Query(DEFAULT_ORDER, description='asc | desc'),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Danh sách nhật ký cảng — 5 bộ lọc của trang thống kê chạy ở SQL.

    Port `StatisticsView.tsx:34-61`: `q` (**chỉ** `track_id` — ô "Track ID (chứa)"),
    `vessel_type_id` (tra loại tàu theo `ship_id` của tàu), `logged_from`/
    `logged_to` (instant UTC — client tự đổi khoảng ngày địa phương) và
    `min_confidence` (thiếu confidence coi là 0). Hai tham số cũ `ship_id` (khớp
    đúng mã tàu — select "Mã tàu (voted_ship_id)" của trang) và `log_date` (một
    ngày lịch) giữ nguyên ngữ nghĩa; `q` và `ship_id` là hai điều kiện độc lập,
    AND với nhau — đúng hai điều khiển riêng của trang.

    `q` cố ý hẹp hơn câu chữ của brief (brief chỉ ghi "`q`"): bản đầu cho `q` khớp
    cả nhãn tàu, tức là superset so với thứ trang biểu đạt được, vì nhãn tàu đã có
    `ship_id` khớp đúng.

    `sort` chỉ nhận `time` (mặc định, = `logged_at`) hoặc `voted_ship_id` — đúng
    hai cột bấm sắp xếp được của bảng; giá trị lạ rơi về mặc định, không bao giờ
    được nội suy vào SQL.
    """
    skip, limit = resolve_page(skip, limit)
    filters = {
        'ship_id': ship_id,
        'log_date': log_date,
        'q': q,
        'vessel_type_id': vessel_type_id,
        'min_confidence': min_confidence,
        'logged_from': as_utc(logged_from),
        'logged_to': as_utc(logged_to),
        'sort': sort,
        'order': order,
    }
    set_total_header(response, port_log_repo.count_logs(db, **filters))
    return port_log_repo.get_all_logs(db, skip=skip, limit=limit, **filters)


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
