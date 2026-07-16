from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date
from typing import List, Optional

from app.db.session import get_db
from app.api.deps import get_current_user
from app.schemas.detection import DetectionCreate, DetectionRead, DetectionUpdate, DetectionVerify
from app.schemas.detection_media import DetectionMediaRead
from app.services.detection_cleanup_service import purge_detection_resources
from app.services.detection_invoice_service import recompute_ai_invoice_for_detection
from app.repositories.detection_repository import detection_repo
from app.repositories.detection_media_repository import detection_media_repo
from app.services.storage.s3_service import presign_get, parse_minio_uri
from app.services.berth_limit_service import compute_detection_over_berth_limit
from app.services.detection_camera_service import resolve_camera_in_out

router = APIRouter()


def _with_presigned_detection_paths(obj):
    for attr in ('audit_image_path', 'video_path'):
        raw = getattr(obj, attr, '') or ''
        if parse_minio_uri(raw) is None:
            continue
        try:
            setattr(obj, attr, presign_get(raw, ttl_seconds=600) or raw)
        except Exception:
            pass
    return obj


def _camera_update(obj, camera_map: Optional[dict]) -> dict:
    if not camera_map:
        return {}
    entry = camera_map.get(str(obj.track_id or ''))
    if not entry:
        return {}
    return {
        'berth_in_camera_id': entry.get('in_camera_id'),
        'berth_in_camera_name': entry.get('in_camera_name'),
        'berth_out_camera_id': entry.get('out_camera_id'),
        'berth_out_camera_name': entry.get('out_camera_name'),
    }


def _detection_to_read(
    db: Session,
    obj,
    *,
    include_over_berth_limit: bool = True,
    include_presigned_paths: bool = True,
    camera_map: Optional[dict] = None,
) -> DetectionRead:
    row = _with_presigned_detection_paths(obj) if include_presigned_paths else obj
    payload = DetectionRead.model_validate(row)
    update = {'is_over_berth_limit': compute_detection_over_berth_limit(db, obj) if include_over_berth_limit else False}
    update.update(_camera_update(obj, camera_map))
    return payload.model_copy(update=update)


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
    created = detection_repo.create(db, payload)
    return _detection_to_read(db, created)


@router.get('/', response_model=List[DetectionRead])
def list_detections(
    skip: int = 0,
    limit: int = 100,
    vessel_id: Optional[int] = None,
    ship_id: Optional[str] = None,
    event_date: Optional[date] = None,
    include_over_berth_limit: bool = False,
    include_presigned_paths: bool = False,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    rows = detection_repo.get_all(
        db,
        skip=skip,
        limit=limit,
        vessel_id=vessel_id,
        ship_id=ship_id,
        event_date=event_date,
    )
    camera_map = resolve_camera_in_out(db, [str(r.track_id or '') for r in rows])
    return [
        _detection_to_read(
            db,
            row,
            include_over_berth_limit=include_over_berth_limit,
            include_presigned_paths=include_presigned_paths,
            camera_map=camera_map,
        )
        for row in rows
    ]


@router.get('/{detection_id}', response_model=DetectionRead)
def get_detection(detection_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    obj = detection_repo.get(db, detection_id)
    if not obj:
        raise HTTPException(status_code=404, detail='Detection not found')
    camera_map = resolve_camera_in_out(db, [str(obj.track_id or '')])
    return _detection_to_read(db, obj, camera_map=camera_map)


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
    return _detection_to_read(db, updated)


@router.patch('/{detection_id}', response_model=DetectionRead)
def update_detection(
    detection_id: int,
    data: DetectionUpdate,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Sửa thông tin detection, sau đó tính lại hóa đơn AI liên kết.

    Hóa đơn AI đã PAID (khóa tài chính) không bị tính lại tiền.
    Response header X-Invoice-Recompute cho biết kết quả tính lại.
    """
    obj = detection_repo.get(db, detection_id)
    if not obj:
        raise HTTPException(status_code=404, detail='Detection not found')

    payload = data.model_dump(exclude_unset=True)
    new_track = payload.get('track_id')
    if new_track and new_track != obj.track_id:
        clash = detection_repo.get_by_track_id(db, new_track)
        if clash and clash.id != detection_id:
            raise HTTPException(status_code=409, detail='track_id already exists')

    try:
        updated = detection_repo.update_fields(db, detection_id, payload, commit=False)
        if not updated:
            raise HTTPException(status_code=404, detail='Detection not found')

        # Existing unpaid invoice and detection update share one transaction.
        invoice_result = recompute_ai_invoice_for_detection(
            detection_id,
            session=db,
            commit=False,
        )
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail='Detection/invoice update failed') from exc

    # No prior invoice: create only after detection commit. Failure cannot leave an
    # existing invoice stale; service logs and returns status without reverting data.
    if invoice_result.get('status') == 'needs_create':
        recompute_ai_invoice_for_detection(detection_id)

    fresh = detection_repo.get(db, detection_id) or updated
    camera_map = resolve_camera_in_out(db, [str(fresh.track_id or '')])
    return _detection_to_read(db, fresh, camera_map=camera_map)


@router.delete('/{detection_id}', status_code=204)
def delete_detection(detection_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    result = purge_detection_resources(db, detection_id)
    if not result.get('found'):
        raise HTTPException(status_code=404, detail='Detection not found')


@router.get('/{detection_id}/media', response_model=List[DetectionMediaRead])
def get_detection_media(detection_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    rows = detection_media_repo.get_by_detection(db, detection_id)
    # If media is stored as minio://bucket/key, convert to a short-lived presigned URL for FE.
    for row in rows:
        if parse_minio_uri(getattr(row, 'file_path', '') or '') is not None:
            try:
                row.file_path = presign_get(row.file_path, ttl_seconds=600) or row.file_path
            except Exception:
                # Keep original value if presign fails; FE will ignore unknown formats.
                pass
    return rows
