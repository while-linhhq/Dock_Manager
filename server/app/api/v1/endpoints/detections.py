from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from datetime import date, datetime
from typing import List, Optional

from app.db.session import get_db
from app.api.deps import get_current_user
from app.schemas.detection import DetectionCreate, DetectionRead, DetectionUpdate, DetectionVerify
from app.schemas.detection_media import DetectionMediaRead
from app.services.detection_cleanup_service import purge_detection_resources
from app.services.detection_invoice_service import recompute_ai_invoice_for_detection
from app.repositories.detection_repository import detection_repo
from app.repositories.detection_media_repository import detection_media_repo
from app.services.storage.s3_service import parse_minio_uri
from app.utils.datetimes import as_utc
from app.utils.media_token import build_media_view_url
from app.utils.pagination import DEFAULT_PAGE_SIZE, resolve_page, set_total_header
from app.services.berth_limit_service import compute_detection_over_berth_limit
from app.services.detection_camera_service import resolve_camera_in_out

router = APIRouter()


def _with_media_view_paths(obj, request):
    """Đổi minio://... thành URL xem được trên trình duyệt (qua chính origin API).

    Trước đây là presign của MinIO — URL đó trỏ thẳng ``MINIO_ENDPOINT``
    (mặc định 127.0.0.1:9100) nên trình duyệt ở máy khác không mở được ảnh.
    """
    for attr in ('audit_image_path', 'video_path'):
        raw = getattr(obj, attr, '') or ''
        if parse_minio_uri(raw) is None:
            continue
        try:
            url = build_media_view_url(raw, request=request)
        except Exception:
            url = None
        if url:
            setattr(obj, attr, url)
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
    request=None,
    include_over_berth_limit: bool = True,
    include_presigned_paths: bool = True,
    camera_map: Optional[dict] = None,
) -> DetectionRead:
    row = _with_media_view_paths(obj, request) if include_presigned_paths else obj
    payload = DetectionRead.model_validate(row)
    update = {'is_over_berth_limit': compute_detection_over_berth_limit(db, obj) if include_over_berth_limit else False}
    update.update(_camera_update(obj, camera_map))
    return payload.model_copy(update=update)


def _first_ocr_result_id(ocr_results: object) -> Optional[str]:
    """id của OCR đầu tiên — đúng thứ `getDetectionShipLabel` của client đọc.

    Client so `typeof id === 'string'` trên `ocr_results[0].id` rồi mới `trim()`,
    nên ở đây **chỉ lọc kiểu**, không trim: chuỗi trả về nguyên bản để phép trim
    vẫn nằm đúng một chỗ như trước (nhãn hiển thị không đổi).
    """
    if not isinstance(ocr_results, list) or not ocr_results:
        return None
    first = ocr_results[0]
    if not isinstance(first, dict):
        return None
    value = first.get('id')
    return value if isinstance(value, str) else None


def _detection_to_lite_row(payload: DetectionRead) -> dict:
    """Bản rút gọn của một dòng danh sách: bỏ hẳn `ocr_results`.

    `ocr_results` chiếm 99,5 % khối lượng phản hồi (đo trên DB thật: 18 dòng →
    2,27 MB) mà sidebar chỉ cần id OCR đầu tiên làm nhãn tàu dự phòng, nên mảng
    đó không cần rời khỏi server. Giữ nguyên mọi trường khác bằng cách rút từ
    chính `DetectionRead` đã dựng (một nguồn duy nhất, không chép tay từng field).
    """
    row = payload.model_dump(mode='json')
    row['first_ocr_result_id'] = _first_ocr_result_id(row.pop('ocr_results', None))
    return row


@router.post('/', response_model=DetectionRead, status_code=201)
def create_detection(
    request: Request,
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
    return _detection_to_read(db, created, request=request)


@router.get('/', response_model=List[DetectionRead])
def list_detections(
    request: Request,
    response: Response,
    skip: int = 0,
    limit: int = DEFAULT_PAGE_SIZE,
    vessel_id: Optional[int] = None,
    ship_id: Optional[str] = None,
    event_date: Optional[date] = None,
    q: Optional[str] = None,
    is_accepted: Optional[bool] = None,
    vessel_type_id: Optional[int] = None,
    occurred_from: Optional[datetime] = None,
    occurred_to: Optional[datetime] = None,
    min_confidence: Optional[float] = None,
    sort: str = 'berth',
    order: str = 'desc',
    include_over_berth_limit: bool = False,
    include_presigned_paths: bool = False,
    include_ocr_results: bool = True,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Danh sách nhận diện — 7 bộ lọc của trang bến chạy ở SQL, kèm sắp xếp cột.

    `q` tìm không phân biệt hoa thường trên nhãn tàu (ship_id / id OCR),
    `track_id` và `vessel_id`; wildcard trong `q` bị escape.
    `occurred_from`/`occurred_to` là instant UTC so với
    `coalesce(start_time, created_at)`; `min_confidence` nhận 0..1.
    `sort` nhận `berth|time|ship_id|confidence|camera|status`, giá trị lạ rơi về
    mặc định `berth` (không bao giờ được nội suy vào SQL). `berth` = thời điểm tàu
    vào vùng neo đậu (`berth_in_time`, fallback `start_time`, `created_at`) — đúng
    thứ tự trang bến đang hiển thị; `time` = thời gian hiển thị của cột "Thời gian".

    `include_ocr_results=False` bỏ hẳn mảng `ocr_results` (99,5 % khối lượng: 18
    dòng ≈ 2,27 MB) và thay bằng `first_ocr_result_id` — đúng id mà
    `getDetectionShipLabel` của client dùng làm nhãn tàu dự phòng. Cờ mặc định
    `True` để mọi caller khác không đổi payload.
    """
    skip, limit = resolve_page(skip, limit)
    occurred_from = as_utc(occurred_from)
    occurred_to = as_utc(occurred_to)
    filters = {
        'vessel_id': vessel_id,
        'ship_id': ship_id,
        'event_date': event_date,
        'q': q,
        'is_accepted': is_accepted,
        'vessel_type_id': vessel_type_id,
        'occurred_from': occurred_from,
        'occurred_to': occurred_to,
        'min_confidence': min_confidence,
        'sort': sort,
        'order': order,
    }
    total = detection_repo.count_filtered(db, **filters)
    set_total_header(response, total)
    rows = detection_repo.get_all(db, skip=skip, limit=limit, **filters)
    camera_map = resolve_camera_in_out(db, [str(r.track_id or '') for r in rows])
    payloads = [
        _detection_to_read(
            db,
            row,
            request=request,
            include_over_berth_limit=include_over_berth_limit,
            include_presigned_paths=include_presigned_paths,
            camera_map=camera_map,
        )
        for row in rows
    ]
    if include_ocr_results:
        return payloads
    # `response_model` của route luôn kèm `ocr_results` (và `response_model_exclude`
    # là cố định theo route, không theo request) nên nhánh rút gọn trả JSON trực
    # tiếp; `model_dump(mode='json')` cho đúng định dạng như FastAPI serialize.
    lite = JSONResponse(content=[_detection_to_lite_row(payload) for payload in payloads])
    # Trả `Response` riêng thì FastAPI bỏ qua `response` được inject ở trên, nên
    # `X-Total-Count` phải đặt lại trên chính response này — nếu không, trang rút
    # gọn mất tổng số dòng (lỗi bắt được khi đo qua HTTP thật).
    set_total_header(lite, total)
    return lite


@router.get('/{detection_id}', response_model=DetectionRead)
def get_detection(detection_id: int, request: Request, db: Session = Depends(get_db), _=Depends(get_current_user)):
    obj = detection_repo.get(db, detection_id)
    if not obj:
        raise HTTPException(status_code=404, detail='Detection not found')
    camera_map = resolve_camera_in_out(db, [str(obj.track_id or '')])
    return _detection_to_read(db, obj, request=request, camera_map=camera_map)


@router.post('/{detection_id}/verify', response_model=DetectionRead)
def verify_detection(
    request: Request,
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
    return _detection_to_read(db, updated, request=request)


@router.patch('/{detection_id}', response_model=DetectionRead)
def update_detection(
    request: Request,
    detection_id: int,
    data: DetectionUpdate,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Sửa thông tin detection, sau đó tính lại hóa đơn AI liên kết.

    Hóa đơn AI đã PARTIAL/PAID (khóa tài chính) không bị tính lại tiền.
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

    fresh = detection_repo.get(db, detection_id) or updated
    camera_map = resolve_camera_in_out(db, [str(fresh.track_id or '')])
    return _detection_to_read(db, fresh, request=request, camera_map=camera_map)


@router.delete('/{detection_id}', status_code=204)
def delete_detection(detection_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    result = purge_detection_resources(db, detection_id)
    if not result.get('found'):
        raise HTTPException(status_code=404, detail='Detection not found')


@router.get('/{detection_id}/media', response_model=List[DetectionMediaRead])
def get_detection_media(
    detection_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    rows = detection_media_repo.get_by_detection(db, detection_id)
    # minio://bucket/key -> URL qua API để trình duyệt (kể cả ở xa) mở được.
    for row in rows:
        raw = getattr(row, 'file_path', '') or ''
        if parse_minio_uri(raw) is None:
            continue
        try:
            url = build_media_view_url(raw, request=request)
        except Exception:
            url = None
        if url:
            row.file_path = url
    return rows
