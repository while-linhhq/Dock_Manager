from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.db.session import get_db
from app.api.deps import get_current_user
from app.schemas.vessel import VesselCreate, VesselUpdate, VesselRead
from app.repositories.vessel_repository import vessel_repo
from app.services.ship_invoice_backfill_service import run_vessel_backfill_task, vessel_ready_for_ai_invoice
from app.services.vessel_read_service import vessel_to_read

router = APIRouter()


def _schedule_vessel_invoice_backfill(background_tasks: BackgroundTasks, vessel_id: int) -> None:
    background_tasks.add_task(run_vessel_backfill_task, vessel_id)


@router.get('/', response_model=List[VesselRead])
def list_vessels(skip: int = 0, limit: int = 100, active_only: bool = False, db: Session = Depends(get_db)):
    vessels = vessel_repo.get_all(db, skip=skip, limit=limit, active_only=active_only)
    return [vessel_to_read(db, v) for v in vessels]


@router.get('/{vessel_id}', response_model=VesselRead)
def get_vessel(vessel_id: int, db: Session = Depends(get_db)):
    vessel = vessel_repo.get(db, vessel_id)
    if not vessel:
        raise HTTPException(status_code=404, detail='Vessel not found')
    return vessel_to_read(db, vessel)


@router.post('/', response_model=VesselRead, status_code=201)
def create_vessel(
    data: VesselCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    if vessel_repo.get_by_ship_id(db, data.ship_id):
        raise HTTPException(status_code=400, detail='Ship ID already exists')
    created = vessel_repo.create(db, data)
    loaded = vessel_repo.get(db, created.id)
    if not loaded:
        raise HTTPException(status_code=500, detail='Failed to load vessel after create')
    if vessel_ready_for_ai_invoice(db, loaded.id):
        _schedule_vessel_invoice_backfill(background_tasks, loaded.id)
    return vessel_to_read(db, loaded)


@router.put('/{vessel_id}', response_model=VesselRead)
def update_vessel(
    vessel_id: int,
    data: VesselUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    before = vessel_repo.get(db, vessel_id)
    if not before:
        raise HTTPException(status_code=404, detail='Vessel not found')

    old_type_id = before.vessel_type_id
    payload = data.model_dump(exclude_none=True)
    updated = vessel_repo.update(db, vessel_id, payload)
    if not updated:
        raise HTTPException(status_code=404, detail='Vessel not found')
    loaded = vessel_repo.get(db, vessel_id)
    if not loaded:
        raise HTTPException(status_code=404, detail='Vessel not found')

    type_changed = 'vessel_type_id' in payload and payload['vessel_type_id'] != old_type_id
    if type_changed and vessel_ready_for_ai_invoice(db, vessel_id):
        _schedule_vessel_invoice_backfill(background_tasks, vessel_id)

    return vessel_to_read(db, loaded)


@router.delete('/{vessel_id}', status_code=204)
def delete_vessel(vessel_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    if not vessel_repo.delete(db, vessel_id):
        raise HTTPException(status_code=404, detail='Vessel not found')
