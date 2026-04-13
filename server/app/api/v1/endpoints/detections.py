from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date
from typing import List, Optional

from app.db.session import get_db
from app.api.deps import get_current_user
from app.schemas.detection import DetectionCreate, DetectionRead, DetectionVerify
from app.schemas.detection_media import DetectionMediaRead
from app.repositories.detection_repository import detection_repo
from app.repositories.detection_media_repository import detection_media_repo

router = APIRouter()


@router.post('/', response_model=DetectionRead, status_code=201)
def create_detection(
    data: DetectionCreate,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    payload = data.model_dump(exclude_unset=True)
    tid = payload.get('track_id')
    if not tid:
        tid = f'mcp_{uuid4().hex}'
        payload['track_id'] = tid
    if detection_repo.get_by_track_id(db, tid):
        raise HTTPException(status_code=409, detail='track_id already exists')
    return detection_repo.create(db, payload)


@router.get('/', response_model=List[DetectionRead])
def list_detections(
    skip: int = 0,
    limit: int = 100,
    vessel_id: Optional[int] = None,
    ship_id: Optional[str] = None,
    event_date: Optional[date] = None,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    return detection_repo.get_all(
        db,
        skip=skip,
        limit=limit,
        vessel_id=vessel_id,
        ship_id=ship_id,
        event_date=event_date,
    )


@router.get('/{detection_id}', response_model=DetectionRead)
def get_detection(detection_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    obj = detection_repo.get(db, detection_id)
    if not obj:
        raise HTTPException(status_code=404, detail='Detection not found')
    return obj


@router.post('/{detection_id}/verify', response_model=DetectionRead)
def verify_detection(
    detection_id: int,
    data: DetectionVerify,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    updated = detection_repo.update_acceptance(
        db,
        detection_id=detection_id,
        is_accepted=data.is_accepted,
        verified_by=current_user.id,
        rejection_reason=data.rejection_reason,
    )
    if not updated:
        raise HTTPException(status_code=404, detail='Detection not found')
    return updated


@router.delete('/{detection_id}', status_code=204)
def delete_detection(detection_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    if not detection_repo.delete(db, detection_id):
        raise HTTPException(status_code=404, detail='Detection not found')


@router.get('/{detection_id}/media', response_model=List[DetectionMediaRead])
def get_detection_media(detection_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return detection_media_repo.get_by_detection(db, detection_id)
