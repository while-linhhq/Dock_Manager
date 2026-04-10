from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.db.session import get_db
from app.api.deps import get_current_user
from app.schemas.vessel_type import VesselTypeCreate, VesselTypeRead
from app.repositories.vessel_type_repository import vessel_type_repo

router = APIRouter()


@router.get('/', response_model=List[VesselTypeRead])
def list_vessel_types(db: Session = Depends(get_db)):
    return vessel_type_repo.get_all(db)


@router.get('/{type_id}', response_model=VesselTypeRead)
def get_vessel_type(type_id: int, db: Session = Depends(get_db)):
    obj = vessel_type_repo.get(db, type_id)
    if not obj:
        raise HTTPException(status_code=404, detail='Vessel type not found')
    return obj


@router.post('/', response_model=VesselTypeRead, status_code=201)
def create_vessel_type(data: VesselTypeCreate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    from app.models.vessel_type import VesselType
    db_obj = VesselType(**data.model_dump())
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj


@router.put('/{type_id}', response_model=VesselTypeRead)
def update_vessel_type(type_id: int, data: VesselTypeCreate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    obj = vessel_type_repo.get(db, type_id)
    if not obj:
        raise HTTPException(status_code=404, detail='Vessel type not found')
    for key, value in data.model_dump(exclude_none=True).items():
        setattr(obj, key, value)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete('/{type_id}', status_code=204)
def delete_vessel_type(type_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    obj = vessel_type_repo.get(db, type_id)
    if not obj:
        raise HTTPException(status_code=404, detail='Vessel type not found')
    db.delete(obj)
    db.commit()
