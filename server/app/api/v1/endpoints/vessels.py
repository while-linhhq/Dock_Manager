from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.db.session import get_db
from app.api.deps import get_current_user
from app.schemas.vessel import VesselCreate, VesselUpdate, VesselRead
from app.repositories.vessel_repository import vessel_repo

router = APIRouter()


@router.get('/', response_model=List[VesselRead])
def list_vessels(skip: int = 0, limit: int = 100, active_only: bool = False, db: Session = Depends(get_db)):
    return vessel_repo.get_all(db, skip=skip, limit=limit, active_only=active_only)


@router.get('/{vessel_id}', response_model=VesselRead)
def get_vessel(vessel_id: int, db: Session = Depends(get_db)):
    vessel = vessel_repo.get(db, vessel_id)
    if not vessel:
        raise HTTPException(status_code=404, detail='Vessel not found')
    return vessel


@router.post('/', response_model=VesselRead, status_code=201)
def create_vessel(data: VesselCreate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    if vessel_repo.get_by_ship_id(db, data.ship_id):
        raise HTTPException(status_code=400, detail='Ship ID already exists')
    return vessel_repo.create(db, data)


@router.put('/{vessel_id}', response_model=VesselRead)
def update_vessel(vessel_id: int, data: VesselUpdate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    updated = vessel_repo.update(db, vessel_id, data.model_dump(exclude_none=True))
    if not updated:
        raise HTTPException(status_code=404, detail='Vessel not found')
    return updated


@router.delete('/{vessel_id}', status_code=204)
def delete_vessel(vessel_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    if not vessel_repo.delete(db, vessel_id):
        raise HTTPException(status_code=404, detail='Vessel not found')
