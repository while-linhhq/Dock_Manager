from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from app.db.session import get_db
from app.api.deps import get_current_user
from app.schemas.order import (
    OrderCreate,
    OrderRead,
    OrderStatusUpdate,
    OrderUpdate,
    normalize_order_status,
)
from app.repositories.order_repository import DEFAULT_ORDER, DEFAULT_SORT, order_repo
from app.services.order_invoice_service import ensure_invoice_for_order
from app.utils.datetimes import as_utc
from app.utils.pagination import DEFAULT_PAGE_SIZE, resolve_page, set_total_header

router = APIRouter()


def _prepare_create_payload(data: OrderCreate, db: Session, user_id: int) -> dict:
    payload = data.model_dump()
    cargo = payload.pop('cargo_details', None)
    desc = payload.pop('description', None)
    payload['description'] = desc if desc is not None else cargo
    payload['status'] = normalize_order_status(payload.get('status'))
    if not (payload.get('order_number') or '').strip():
        payload['order_number'] = order_repo.generate_unique_order_number(db)
    payload['created_by'] = payload.get('created_by') or user_id
    return payload


@router.get('/', response_model=List[OrderRead])
def list_orders(
    response: Response,
    skip: int = 0,
    limit: int = DEFAULT_PAGE_SIZE,
    status: Optional[str] = None,
    q: Optional[str] = Query(
        None,
        description='Tìm không phân biệt hoa thường: id đơn, ship_id / tên tàu, mô tả hàng hoá',
    ),
    vessel_id: Optional[int] = None,
    vessel_type_id: Optional[int] = None,
    created_from: Optional[datetime] = Query(
        None, description='Instant UTC (ISO-8601) so với created_at'
    ),
    created_to: Optional[datetime] = Query(
        None, description='Instant UTC (ISO-8601) so với created_at'
    ),
    min_total: Optional[Decimal] = None,
    max_total: Optional[Decimal] = None,
    sort: str = Query(
        DEFAULT_SORT,
        description='created_at | order_code | vessel | status | total_amount',
    ),
    order: str = Query(DEFAULT_ORDER, description='asc | desc'),
    db: Session = Depends(get_db),
):
    """Danh sách đơn hàng — 8 bộ lọc của trang đơn hàng chạy ở SQL, kèm sắp xếp cột.

    Port `OrdersView.tsx:40-80`: `q` (id đơn / ship_id / tên tàu / mô tả hàng hoá;
    wildcard bị escape), `status` (chuẩn hoá như cũ), `vessel_id`,
    `vessel_type_id`, `created_from`/`created_to` (instant UTC so với `created_at`)
    và `min_total`/`max_total` (client coi số tiền thiếu là 0).

    `sort` chỉ nhận các khóa trong whitelist của `order_repository`
    (`created_at` mặc định), giá trị lạ rơi về mặc định — không bao giờ được nội
    suy vào SQL.
    """
    norm = normalize_order_status(status) if status else None
    skip, limit = resolve_page(skip, limit)
    filters = {
        'status': norm,
        'q': q,
        'vessel_id': vessel_id,
        'vessel_type_id': vessel_type_id,
        'created_from': as_utc(created_from),
        'created_to': as_utc(created_to),
        'min_total': min_total,
        'max_total': max_total,
        'sort': sort,
        'order': order,
    }
    total = order_repo.count_filtered(db, **filters)
    set_total_header(response, total)
    return order_repo.get_all(db, skip=skip, limit=limit, **filters)


@router.get('/{order_id}', response_model=OrderRead)
def get_order(order_id: int, db: Session = Depends(get_db)):
    obj = order_repo.get(db, order_id)
    if not obj:
        raise HTTPException(status_code=404, detail='Order not found')
    return obj


@router.post('/', response_model=OrderRead, status_code=201)
def create_order(data: OrderCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    payload = _prepare_create_payload(data, db, current_user.id)
    order = order_repo.create(db, payload, commit=False)
    try:
        ensure_invoice_for_order(db, order, current_user.id)
    except Exception:
        db.rollback()
        raise
    loaded = order_repo.get(db, order.id)
    return loaded if loaded is not None else order


@router.put('/{order_id}', response_model=OrderRead)
def update_order(order_id: int, data: OrderUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    payload = data.model_dump(exclude_none=True)
    if 'cargo_details' in payload:
        payload['description'] = payload.pop('cargo_details')
    if 'status' in payload:
        payload['status'] = normalize_order_status(payload['status'])
    payload['updated_by'] = current_user.id
    updated = order_repo.update(db, order_id, payload)
    if not updated:
        raise HTTPException(status_code=404, detail='Order not found')
    return updated


@router.patch('/{order_id}/status', response_model=OrderRead)
def update_order_status(order_id: int, data: OrderStatusUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    st = normalize_order_status(data.status)
    updated = order_repo.update_status(db, order_id, st, updated_by=current_user.id)
    if not updated:
        raise HTTPException(status_code=404, detail='Order not found')
    return updated


@router.delete('/{order_id}', status_code=204)
def delete_order(order_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    if not order_repo.delete(db, order_id):
        raise HTTPException(status_code=404, detail='Order not found')
