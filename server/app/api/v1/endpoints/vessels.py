import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, List

import cv2
import numpy as np
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.deps import get_current_user
from app.core.config import settings
from app.schemas.vessel import VesselCreate, VesselUpdate, VesselRead
from app.repositories.vessel_repository import vessel_repo
from app.services.ai.vector_store_qdrant import QdrantVectorStore
from app.services.ai.visual_embedding_extractor import VisualEmbeddingExtractor
from app.services.ship_invoice_backfill_service import run_vessel_backfill_task, vessel_ready_for_ai_invoice
from app.services.vessel_read_service import vessel_to_read
from app.services.storage.minio_layout import visual_reference_preview_key
from app.services.storage.minio_service import (
    get_object_bytes,
    parse_minio_uri,
    presign_get,
    put_bytes,
    remove_object,
)

_log = logging.getLogger(__name__)
_PREVIEW_MAX_SIDE = 320
_PREVIEW_JPEG_QUALITY = 85
_SERVER_ROOT = Path(__file__).resolve().parents[4]
_LOCAL_PREVIEW_ROOT = _SERVER_ROOT / 'data' / 'visual-references'
_LOCAL_PREVIEW_URI_PREFIX = 'local://'

router = APIRouter()

_visual_extractor: VisualEmbeddingExtractor | None = None
_visual_extractor_lock = Lock()


def _get_visual_extractor() -> VisualEmbeddingExtractor:
    global _visual_extractor
    with _visual_extractor_lock:
        if _visual_extractor is None:
            _visual_extractor = VisualEmbeddingExtractor(
                model_path=settings.VISUAL_MODEL_PATH or None,
                backbone=settings.VISUAL_BACKBONE,
                device=settings.VISUAL_DEVICE or settings.DEVICE,
                embedding_dim=settings.VISUAL_EMBEDDING_DIM,
            )
        return _visual_extractor


def _get_qdrant_store(*, vector_size: int) -> QdrantVectorStore:
    return QdrantVectorStore(
        host=settings.QDRANT_HOST,
        port=int(settings.QDRANT_PORT),
        api_key=settings.QDRANT_API_KEY or None,
        collection_name=settings.QDRANT_COLLECTION,
        vector_size=int(vector_size),
        distance=settings.QDRANT_DISTANCE,
    )


def _encode_preview_jpeg(frame: np.ndarray, *, max_side: int = _PREVIEW_MAX_SIDE) -> bytes | None:
    if frame is None or frame.size == 0:
        return None
    height, width = frame.shape[:2]
    scale = min(1.0, float(max_side) / max(height, width))
    if scale < 1.0:
        resized = cv2.resize(
            frame,
            (max(1, int(width * scale)), max(1, int(height * scale))),
            interpolation=cv2.INTER_AREA,
        )
    else:
        resized = frame
    ok, encoded = cv2.imencode(
        '.jpg',
        resized,
        [int(cv2.IMWRITE_JPEG_QUALITY), int(_PREVIEW_JPEG_QUALITY)],
    )
    return encoded.tobytes() if ok else None


def _safe_path_segment(raw: str) -> str:
    cleaned = ''.join(ch if ch.isalnum() or ch in ('-', '_', '.') else '_' for ch in str(raw).strip())
    return cleaned.strip('._-') or 'unknown'


def _local_preview_rel(ship_id: str, point_id: str) -> str:
    return f'{_safe_path_segment(ship_id)}/{_safe_path_segment(point_id)}.jpg'


def _local_preview_path(ship_id: str, point_id: str) -> Path:
    return _LOCAL_PREVIEW_ROOT / _local_preview_rel(ship_id, point_id)


def _save_visual_preview_local(jpeg: bytes, *, ship_id: str, point_id: str) -> str:
    path = _local_preview_path(ship_id, point_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(jpeg)
    return f'{_LOCAL_PREVIEW_URI_PREFIX}{_local_preview_rel(ship_id, point_id)}'


def _upload_visual_preview(
    frame: np.ndarray,
    *,
    ship_id: str,
    point_id: str,
) -> str | None:
    jpeg = _encode_preview_jpeg(frame)
    if not jpeg:
        return None

    bucket = str(getattr(settings, 'MINIO_BUCKET', '') or '').strip() or 'media'
    object_key = visual_reference_preview_key(ship_id, point_id)
    try:
        put_bytes(
            data=jpeg,
            bucket=bucket,
            object_key=object_key,
            content_type='image/jpeg',
        )
        return f'minio://{bucket}/{object_key}'
    except Exception:
        _log.warning(
            'MinIO preview upload failed, using local storage ship_id=%s point_id=%s',
            ship_id,
            point_id,
            exc_info=True,
        )

    try:
        return _save_visual_preview_local(jpeg, ship_id=ship_id, point_id=point_id)
    except Exception:
        _log.exception(
            'Failed to save local visual reference preview ship_id=%s point_id=%s',
            ship_id,
            point_id,
        )
        return None


def _preview_api_path(vessel_id: int, point_id: str) -> str:
    return f'/api/v1/vessels/{vessel_id}/visual-enroll/{point_id}/preview'


def _resolve_preview_url(
    *,
    vessel_id: int,
    point_id: str,
    ship_id: str,
    preview_uri: str | None,
) -> str | None:
    uri = str(preview_uri or '').strip()
    if uri.startswith(_LOCAL_PREVIEW_URI_PREFIX):
        return _preview_api_path(vessel_id, point_id)
    if uri.startswith('minio://'):
        try:
            url = presign_get(uri, ttl_seconds=600)
            if url:
                return url
        except Exception:
            _log.exception('Failed to presign visual reference preview uri=%s', uri)

    if _local_preview_path(ship_id, point_id).is_file():
        return _preview_api_path(vessel_id, point_id)
    return None


def _enrich_visual_reference_item(
    item: dict[str, Any],
    *,
    vessel_id: int,
    ship_id: str,
) -> dict[str, Any]:
    payload = dict(item.get('payload') or {})
    point_id = str(item.get('id') or '')
    preview_url = _resolve_preview_url(
        vessel_id=vessel_id,
        point_id=point_id,
        ship_id=ship_id,
        preview_uri=str(payload.get('preview_uri') or '') or None,
    )
    return {
        'id': point_id,
        'payload': payload,
        'preview_url': preview_url,
    }


def _delete_visual_preview(*, ship_id: str, point_id: str, preview_uri: str | None = None) -> None:
    uri = str(preview_uri or '').strip()
    if uri.startswith(_LOCAL_PREVIEW_URI_PREFIX):
        rel = uri[len(_LOCAL_PREVIEW_URI_PREFIX) :]
        try:
            (_LOCAL_PREVIEW_ROOT / rel).unlink(missing_ok=True)
        except Exception:
            _log.warning('Could not remove local visual reference preview %s', rel)
        return

    ref = parse_minio_uri(uri)
    if ref is not None:
        try:
            remove_object(bucket=ref.bucket, object_key=ref.object_key)
        except Exception:
            _log.warning(
                'Could not remove MinIO visual reference preview bucket=%s key=%s',
                ref.bucket,
                ref.object_key,
            )

    try:
        _local_preview_path(ship_id, point_id).unlink(missing_ok=True)
    except Exception:
        pass


def _decode_upload_image(content: bytes) -> np.ndarray:
    if not content:
        raise HTTPException(status_code=400, detail='Uploaded image is empty')
    arr = np.frombuffer(content, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None or frame.size == 0:
        raise HTTPException(status_code=400, detail='Invalid image format')
    return frame


def _resolve_qdrant_vector_size(extractor: VisualEmbeddingExtractor) -> int:
    probe = _get_qdrant_store(vector_size=extractor.vector_dim)
    if not probe.healthcheck():
        raise HTTPException(status_code=503, detail='Qdrant is unavailable')
    collection_size = probe.collection_vector_size()
    if collection_size is not None:
        return collection_size
    return extractor.vector_dim


def _enroll_visual_reference(
    *,
    vessel: Any,
    frame: np.ndarray,
    filename: str,
    extractor: VisualEmbeddingExtractor,
    qdrant: QdrantVectorStore,
    vector_size: int,
) -> dict[str, Any]:
    embedding = extractor.extract(frame)
    if embedding is None:
        raise HTTPException(status_code=500, detail='Failed to extract visual embedding')
    if embedding.shape[0] != vector_size:
        raise HTTPException(
            status_code=400,
            detail=(
                f'Embedding size mismatch: got {embedding.shape[0]}, '
                f'expected {vector_size}. '
                'Align VISUAL_EMBEDDING_DIM / QDRANT_VECTOR_SIZE with the ViT backbone '
                'or recreate the Qdrant collection.'
            ),
        )

    enrolled_at = datetime.now(timezone.utc).isoformat()
    # Qdrant accepts only unsigned int or standard UUID (not custom string prefixes).
    point_id = str(uuid.uuid4())
    preview_uri = _upload_visual_preview(
        frame,
        ship_id=str(vessel.ship_id),
        point_id=point_id,
    )
    payload: dict[str, Any] = {
        'vessel_id': int(vessel.id),
        'ship_id': str(vessel.ship_id),
        'vessel_name': str(vessel.name or ''),
        'filename': str(filename or ''),
        'enrolled_at': enrolled_at,
        'source': 'manual-upload',
    }
    if preview_uri:
        payload['preview_uri'] = preview_uri
    stored = qdrant.upsert(
        point_id=point_id,
        embedding=embedding,
        payload=payload,
    )
    if not stored:
        raise HTTPException(
            status_code=502,
            detail='Failed to store visual embedding in Qdrant',
        )
    return {
        'ok': True,
        'vessel_id': int(vessel.id),
        'ship_id': str(vessel.ship_id),
        'point_id': point_id,
        'filename': str(filename or ''),
        'source': 'manual-upload',
        'enrolled_at': enrolled_at,
        'preview_url': _resolve_preview_url(
            vessel_id=int(vessel.id),
            point_id=point_id,
            ship_id=str(vessel.ship_id),
            preview_uri=preview_uri,
        ),
    }


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


@router.post('/{vessel_id}/visual-enroll')
async def enroll_vessel_visual_reference(
    vessel_id: int,
    images: List[UploadFile] = File(..., description='One or more reference images'),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    vessel = vessel_repo.get(db, vessel_id)
    if not vessel:
        raise HTTPException(status_code=404, detail='Vessel not found')
    if not images:
        raise HTTPException(status_code=400, detail='At least one image is required')

    extractor = _get_visual_extractor()
    if extractor.backend == 'unavailable':
        raise HTTPException(status_code=503, detail='Visual embedding model is unavailable')

    vector_size = _resolve_qdrant_vector_size(extractor)
    qdrant = _get_qdrant_store(vector_size=vector_size)

    enrolled: list[dict[str, Any]] = []
    failed: list[dict[str, str]] = []

    for index, upload in enumerate(images):
        filename = str(upload.filename or f'image_{index + 1}')
        try:
            content = await upload.read()
            frame = _decode_upload_image(content)
            enrolled.append(
                _enroll_visual_reference(
                    vessel=vessel,
                    frame=frame,
                    filename=filename,
                    extractor=extractor,
                    qdrant=qdrant,
                    vector_size=vector_size,
                )
            )
        except HTTPException as err:
            failed.append({'filename': filename, 'detail': str(err.detail)})
        except Exception:
            failed.append({'filename': filename, 'detail': 'Unexpected error during enrollment'})

    if not enrolled:
        detail = failed[0]['detail'] if failed else 'No images could be enrolled'
        raise HTTPException(status_code=400, detail=detail)

    if len(enrolled) == 1 and not failed:
        return enrolled[0]

    return {
        'ok': True,
        'vessel_id': int(vessel.id),
        'ship_id': str(vessel.ship_id),
        'count': len(enrolled),
        'enrolled': enrolled,
        'failed': failed,
    }


@router.get('/{vessel_id}/visual-enroll')
def list_vessel_visual_references(
    vessel_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    vessel = vessel_repo.get(db, vessel_id)
    if not vessel:
        raise HTTPException(status_code=404, detail='Vessel not found')

    extractor = _get_visual_extractor()
    vector_size = _resolve_qdrant_vector_size(extractor)
    qdrant = _get_qdrant_store(vector_size=vector_size)
    if not qdrant.healthcheck():
        raise HTTPException(status_code=503, detail='Qdrant is unavailable')

    points = qdrant.list_by_ship_id(ship_id=str(vessel.ship_id), limit=200)
    items = [
        _enrich_visual_reference_item(
            point,
            vessel_id=int(vessel.id),
            ship_id=str(vessel.ship_id),
        )
        for point in points
    ]
    return {
        'vessel_id': int(vessel.id),
        'ship_id': str(vessel.ship_id),
        'count': len(items),
        'items': items,
    }


@router.get('/{vessel_id}/visual-enroll/{point_id}/preview')
def get_vessel_visual_reference_preview(
    vessel_id: int,
    point_id: str,
    db: Session = Depends(get_db),
):
    """Serve JPEG thumbnail for a visual reference (local disk or MinIO bytes)."""
    vessel = vessel_repo.get(db, vessel_id)
    if not vessel:
        raise HTTPException(status_code=404, detail='Vessel not found')

    local_path = _local_preview_path(str(vessel.ship_id), point_id)
    if local_path.is_file():
        return FileResponse(local_path, media_type='image/jpeg')

    extractor = _get_visual_extractor()
    vector_size = _resolve_qdrant_vector_size(extractor)
    qdrant = _get_qdrant_store(vector_size=vector_size)
    if qdrant.healthcheck():
        for point in qdrant.list_by_ship_id(ship_id=str(vessel.ship_id), limit=500):
            if str(point.get('id')) != str(point_id):
                continue
            preview_uri = str((point.get('payload') or {}).get('preview_uri') or '')
            if preview_uri.startswith('minio://'):
                data = get_object_bytes(preview_uri)
                if data:
                    return Response(content=data, media_type='image/jpeg')
            break

    raise HTTPException(status_code=404, detail='Preview image not found')


@router.delete('/{vessel_id}/visual-enroll/{point_id}')
def delete_vessel_visual_reference(
    vessel_id: int,
    point_id: str,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    vessel = vessel_repo.get(db, vessel_id)
    if not vessel:
        raise HTTPException(status_code=404, detail='Vessel not found')

    extractor = _get_visual_extractor()
    vector_size = _resolve_qdrant_vector_size(extractor)
    qdrant = _get_qdrant_store(vector_size=vector_size)
    if not qdrant.healthcheck():
        raise HTTPException(status_code=503, detail='Qdrant is unavailable')

    preview_uri: str | None = None
    for point in qdrant.list_by_ship_id(ship_id=str(vessel.ship_id), limit=500):
        if str(point.get('id')) == str(point_id):
            preview_uri = str((point.get('payload') or {}).get('preview_uri') or '') or None
            break

    if not qdrant.delete_point(point_id=point_id):
        raise HTTPException(status_code=500, detail='Failed to delete visual reference')

    _delete_visual_preview(
        ship_id=str(vessel.ship_id),
        point_id=str(point_id),
        preview_uri=preview_uri,
    )
    return {'ok': True, 'point_id': point_id}
