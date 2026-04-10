from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.db.session import get_db
from app.api.deps import get_current_user
from app.schemas.camera import CameraCreate, CameraUpdate, CameraRead
from app.repositories.camera_repository import camera_repo

router = APIRouter()


@router.get('/', response_model=List[CameraRead])
def list_cameras(active_only: bool = False, db: Session = Depends(get_db), _=Depends(get_current_user)):
    """List all cameras."""
    if active_only:
        return camera_repo.get_active(db)
    return camera_repo.get_all(db)


@router.get('/{camera_id}', response_model=CameraRead)
def get_camera(camera_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    obj = camera_repo.get(db, camera_id)
    if not obj:
        raise HTTPException(status_code=404, detail='Camera not found')
    return obj


@router.post('/', response_model=CameraRead, status_code=201)
def create_camera(data: CameraCreate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    from app.models.camera import Camera
    db_obj = Camera(**data.model_dump())
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj


@router.put('/{camera_id}', response_model=CameraRead)
def update_camera(camera_id: int, data: CameraUpdate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    obj = camera_repo.get(db, camera_id)
    if not obj:
        raise HTTPException(status_code=404, detail='Camera not found')
    for key, value in data.model_dump(exclude_none=True).items():
        setattr(obj, key, value)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete('/{camera_id}', status_code=204)
def delete_camera(camera_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    obj = camera_repo.get(db, camera_id)
    if not obj:
        raise HTTPException(status_code=404, detail='Camera not found')
    db.delete(obj)
    db.commit()
