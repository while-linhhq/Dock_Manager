from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.session import get_db
from app.api.deps import get_current_user
from app.models.vessel import Vessel
from app.schemas.vessel_type import (
    VesselTypeCreate,
    VesselTypeMemberVessel,
    VesselTypeRead,
)
from app.repositories.vessel_type_repository import vessel_type_repo
from app.services.ship_invoice_backfill_service import run_vessel_backfill_task
from app.utils.pagination import (
    DEFAULT_CATALOG_LIMIT,
    MAX_CATALOG_LIMIT,
    resolve_page,
    set_total_header,
)

router = APIRouter()


def _sync_type_members(db: Session, type_id: int, member_vessel_ids: Optional[List[int]]) -> list[int]:
    """Đồng bộ danh sách tàu (tháng) thuộc một loại.

    - member_vessel_ids = None: không đụng gì (giữ nguyên).
    - Tàu trong danh sách  -> vessel_type_id = type_id, classification = 'monthly'.
    - Tàu ĐANG thuộc loại nhưng KHÔNG còn trong danh sách -> gỡ ra:
      vessel_type_id = NULL, classification = 'unclassified'.
    Không đổi phân loại của tàu lẻ (spot) — chỉ tàu được chọn mới thành monthly.
    """
    if member_vessel_ids is None:
        return []
    desired = set(member_vessel_ids)
    changed: set[int] = set()

    # Gỡ tàu cũ không còn được chọn.
    current = db.query(Vessel).filter(Vessel.vessel_type_id == type_id).all()
    for v in current:
        if v.id not in desired:
            changed.add(v.id)
            v.vessel_type_id = None
            v.classification = 'unclassified'

    # Gán tàu được chọn -> monthly + trỏ về loại này.
    if desired:
        chosen = db.query(Vessel).filter(Vessel.id.in_(desired)).all()
        found_ids = {v.id for v in chosen}
        missing = desired - found_ids
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f'Vessel id không tồn tại: {sorted(missing)}',
            )
        spot_ids = sorted(v.id for v in chosen if v.classification == 'spot')
        if spot_ids:
            raise HTTPException(
                status_code=422,
                detail=f'Không thể gán tàu lẻ vào loại tàu tháng: {spot_ids}',
            )
        for v in chosen:
            if v.vessel_type_id != type_id or v.classification != 'monthly':
                changed.add(v.id)
            v.vessel_type_id = type_id
            v.classification = 'monthly'
    return sorted(changed)


@router.get('/', response_model=List[VesselTypeRead])
def list_vessel_types(
    response: Response,
    skip: int = 0,
    limit: int = DEFAULT_CATALOG_LIMIT,
    db: Session = Depends(get_db),
):
    skip, limit = resolve_page(skip, limit, max_limit=MAX_CATALOG_LIMIT)
    set_total_header(response, vessel_type_repo.count_all(db))
    return vessel_type_repo.get_all(db, skip=skip, limit=limit)


@router.get('/assignable-vessels', response_model=List[VesselTypeMemberVessel])
def list_assignable_vessels(db: Session = Depends(get_db)):
    """Tàu có thể gán vào loại (picker): tàu tháng + tàu chưa phân loại.

    Loại trừ tàu lẻ (spot) vì tàu lẻ tính phí per-tàu, không theo loại.
    """
    return (
        db.query(Vessel)
        .filter(Vessel.classification.in_(['monthly', 'unclassified']))
        .order_by(Vessel.ship_id.asc())
        .all()
    )


@router.get('/{type_id}', response_model=VesselTypeRead)
def get_vessel_type(type_id: int, db: Session = Depends(get_db)):
    obj = vessel_type_repo.get(db, type_id)
    if not obj:
        raise HTTPException(status_code=404, detail='Vessel type not found')
    return obj


@router.get('/{type_id}/members', response_model=List[VesselTypeMemberVessel])
def list_type_members(type_id: int, db: Session = Depends(get_db)):
    """Danh sách tàu hiện đang thuộc một loại."""
    obj = vessel_type_repo.get(db, type_id)
    if not obj:
        raise HTTPException(status_code=404, detail='Vessel type not found')
    return (
        db.query(Vessel)
        .filter(Vessel.vessel_type_id == type_id)
        .order_by(Vessel.ship_id.asc())
        .all()
    )


@router.post('/', response_model=VesselTypeRead, status_code=201)
def create_vessel_type(
    data: VesselTypeCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    from app.models.vessel_type import VesselType
    payload = data.model_dump(exclude={'member_vessel_ids'})
    db_obj = VesselType(**payload)
    db.add(db_obj)
    db.flush()  # cần id để gán membership trong cùng transaction
    changed_ids = _sync_type_members(db, db_obj.id, data.member_vessel_ids)
    db.commit()
    for vessel_id in changed_ids:
        background_tasks.add_task(run_vessel_backfill_task, vessel_id)
    db.refresh(db_obj)
    return db_obj


@router.put('/{type_id}', response_model=VesselTypeRead)
def update_vessel_type(
    type_id: int,
    data: VesselTypeCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    obj = vessel_type_repo.get(db, type_id)
    if not obj:
        raise HTTPException(status_code=404, detail='Vessel type not found')
    # exclude_none để member_vessel_ids=None (không gửi) không xóa membership;
    # nhưng vẫn cho [] xóa sạch -> tách riêng.
    for key, value in data.model_dump(exclude={'member_vessel_ids'}, exclude_none=True).items():
        setattr(obj, key, value)
    changed_ids = _sync_type_members(db, type_id, data.member_vessel_ids)
    db.commit()
    for vessel_id in changed_ids:
        background_tasks.add_task(run_vessel_backfill_task, vessel_id)
    db.refresh(obj)
    return obj


@router.delete('/{type_id}', status_code=204)
def delete_vessel_type(type_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    obj = vessel_type_repo.get(db, type_id)
    if not obj:
        raise HTTPException(status_code=404, detail='Vessel type not found')
    db.delete(obj)
    db.commit()
