from datetime import date, datetime, time, timezone
from sqlalchemy import String, case, cast, func, or_, select
from sqlalchemy.orm import Query, Session, joinedload
from app.models.boundary_crossing_event import BoundaryCrossingEvent
from app.models.camera import Camera
from app.models.detection import Detection
from app.models.vessel import Vessel
from app.utils.sql_filters import ilike_contains
from typing import List, Optional

# Nhãn hiển thị khi detection chưa gắn tàu và OCR không đọc được id nào — giữ
# đúng chuỗi client dùng trong `getDetectionShipLabel`.
UNKNOWN_SHIP_LABEL = 'KHÔNG XÁC ĐỊNH'

DEFAULT_SORT = 'time'
DEFAULT_ORDER = 'desc'


def _ship_label_expr():
    """Nhãn tàu hiển thị, port từ `getDetectionShipLabel` của client.

    Ưu tiên `vessels.ship_id`, rồi id OCR đầu tiên, cuối cùng là nhãn "không xác
    định". Cần JOIN `vessels` kiểu outer. `btrim` chỉ cắt khoảng trắng ASCII còn
    `String.trim()` của client rộng hơn, nhưng ship_id thực tế không có ký tự lạ.
    """
    return func.coalesce(
        func.nullif(func.btrim(Vessel.ship_id), ''),
        func.nullif(func.jsonb_extract_path_text(Detection.ocr_results, '0', 'id'), ''),
        UNKNOWN_SHIP_LABEL,
    )


def _camera_in_name_expr():
    """Tên camera lúc tàu IN vùng neo đậu — cùng nguồn với `resolve_camera_in_out`.

    Detection không lưu camera_id: camera IN là event 'in' sớm nhất theo track_id
    trong `boundary_crossing_events`, tên lấy từ bảng `cameras`.
    """
    return (
        select(Camera.camera_name)
        .select_from(BoundaryCrossingEvent)
        .join(Camera, Camera.id == BoundaryCrossingEvent.camera_id)
        .where(
            BoundaryCrossingEvent.track_id == Detection.track_id,
            BoundaryCrossingEvent.direction == 'in',
            BoundaryCrossingEvent.camera_id.isnot(None),
        )
        .order_by(BoundaryCrossingEvent.crossed_at.asc(), BoundaryCrossingEvent.id.asc())
        .limit(1)
        .correlate(Detection)
        .scalar_subquery()
    )


def _status_expr():
    """Trạng thái duyệt — đúng hai chuỗi client dùng để sắp xếp cột trạng thái."""
    return case((Detection.is_accepted.is_(True), 'Đã Xác Nhận'), else_='Chờ Duyệt')


# Whitelist cột sắp xếp: `sort` của client chỉ được TRA CỨU ở đây, không bao giờ
# được nội suy thành tên cột.
SORT_COLUMNS = {
    'time': lambda: func.coalesce(Detection.start_time, Detection.created_at),
    'ship_id': _ship_label_expr,
    'confidence': lambda: func.coalesce(Detection.confidence, 0.0),
    'camera': _camera_in_name_expr,
    'status': _status_expr,
}

# Khóa sort cần JOIN `vessels` mới dựng được biểu thức.
VESSEL_JOIN_SORTS = frozenset({'ship_id'})


class DetectionRepository:
    def get(self, db: Session, detection_id: int) -> Optional[Detection]:
        return (
            db.query(Detection)
            .options(joinedload(Detection.vessel))
            .filter(Detection.id == detection_id)
            .first()
        )

    def get_by_track_id(self, db: Session, track_id: str) -> Optional[Detection]:
        return db.query(Detection).filter(Detection.track_id == track_id).first()

    def _filtered_query(
        self,
        db: Session,
        *,
        vessel_id: Optional[int] = None,
        ship_id: Optional[str] = None,
        event_date: Optional[date] = None,
        q: Optional[str] = None,
        is_accepted: Optional[bool] = None,
        vessel_type_id: Optional[int] = None,
        occurred_from: Optional[datetime] = None,
        occurred_to: Optional[datetime] = None,
        min_confidence: Optional[float] = None,
        sort: str = DEFAULT_SORT,
        order: str = DEFAULT_ORDER,
    ) -> Query:
        """Query đã áp bộ lọc + sắp xếp, dùng chung cho `get_all` và `count_filtered`.

        Nhờ dùng chung một chỗ dựng query, `X-Total-Count` luôn khớp đúng tập
        bản ghi mà danh sách trả về (kể cả khi bộ lọc đổi về sau).

        Bộ lọc port từ trang bến (`PortView`), gồm 7 bộ lọc:
        `q`, `is_accepted`, `vessel_id`, `vessel_type_id`, `occurred_from`,
        `occurred_to`, `min_confidence`. `occurred_from`/`occurred_to` là instant
        UTC so với `coalesce(start_time, created_at)`; `min_confidence` nhận 0..1
        (client chia phần trăm cho 100 trước khi gửi).

        Mọi thứ tự đều kết thúc bằng `detections.id` làm tiebreaker để phân trang
        không trả trùng hoặc mất row khi nhiều row cùng khóa sắp xếp.
        """
        query = db.query(Detection).filter(Detection.deleted_at.is_(None))
        joined_vessel = False

        def with_vessel(current: Query) -> Query:
            """JOIN `vessels` đúng một lần, kiểu outer để không mất row chưa gắn tàu."""
            nonlocal joined_vessel
            if not joined_vessel:
                current = current.outerjoin(Vessel, Detection.vessel_id == Vessel.id)
                joined_vessel = True
            return current

        if vessel_id is not None:
            query = query.filter(Detection.vessel_id == vessel_id)
        if ship_id:
            normalized = ship_id.strip().upper()
            if normalized:
                query = with_vessel(query).filter(
                    func.upper(func.trim(Vessel.ship_id)) == normalized
                )
        if vessel_type_id is not None:
            query = with_vessel(query).filter(Vessel.vessel_type_id == vessel_type_id)
        if q and q.strip():
            # Cùng 4 trường client đưa vào `matchesAnyField`: nhãn hiển thị (đã
            # gồm `vessels.ship_id`), track_id, vessel_id dạng chuỗi và ship_id thô.
            needle = q.strip()
            query = with_vessel(query).filter(
                or_(
                    ilike_contains(Detection.track_id, needle),
                    ilike_contains(cast(Detection.vessel_id, String), needle),
                    ilike_contains(Vessel.ship_id, needle),
                    ilike_contains(_ship_label_expr(), needle),
                )
            )
        if is_accepted is not None:
            # Client: "chưa duyệt" là `is_accepted !== true` nên gồm cả NULL.
            query = query.filter(
                Detection.is_accepted.is_(True)
                if is_accepted
                else Detection.is_accepted.isnot(True)
            )
        if occurred_from is not None:
            query = query.filter(
                func.coalesce(Detection.start_time, Detection.created_at) >= occurred_from
            )
        if occurred_to is not None:
            query = query.filter(
                func.coalesce(Detection.start_time, Detection.created_at) <= occurred_to
            )
        if min_confidence is not None:
            # Client coi confidence thiếu là 0 (`det.confidence ?? 0`).
            query = query.filter(
                func.coalesce(Detection.confidence, 0.0) >= min_confidence
            )
        if event_date is not None:
            start_dt = datetime.combine(event_date, time.min, tzinfo=timezone.utc)
            end_dt = datetime.combine(event_date, time.max, tzinfo=timezone.utc)
            query = query.filter(
                func.coalesce(Detection.start_time, Detection.created_at) >= start_dt,
                func.coalesce(Detection.start_time, Detection.created_at) <= end_dt,
            )

        key = (sort or '').strip().lower()
        column_factory = SORT_COLUMNS.get(key)
        if column_factory is None:
            key = DEFAULT_SORT
            column_factory = SORT_COLUMNS[DEFAULT_SORT]
        if key in VESSEL_JOIN_SORTS:
            query = with_vessel(query)
        column = column_factory()
        if key == 'camera':
            column = func.nullif(column, '')

        ascending = (order or '').strip().lower() == 'asc'
        ordered = column.asc() if ascending else column.desc()
        tiebreaker = Detection.id.asc() if ascending else Detection.id.desc()
        # Giá trị rỗng luôn xuống cuối ở cả hai chiều, giống `sortRows` của client.
        return query.order_by(ordered.nullslast(), tiebreaker)

    def get_all(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        vessel_id: Optional[int] = None,
        ship_id: Optional[str] = None,
        event_date: Optional[date] = None,
        q: Optional[str] = None,
        is_accepted: Optional[bool] = None,
        vessel_type_id: Optional[int] = None,
        occurred_from: Optional[datetime] = None,
        occurred_to: Optional[datetime] = None,
        min_confidence: Optional[float] = None,
        sort: str = DEFAULT_SORT,
        order: str = DEFAULT_ORDER,
    ) -> List[Detection]:
        return (
            self._filtered_query(
                db,
                vessel_id=vessel_id,
                ship_id=ship_id,
                event_date=event_date,
                q=q,
                is_accepted=is_accepted,
                vessel_type_id=vessel_type_id,
                occurred_from=occurred_from,
                occurred_to=occurred_to,
                min_confidence=min_confidence,
                sort=sort,
                order=order,
            )
            .options(joinedload(Detection.vessel))
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count_filtered(
        self,
        db: Session,
        *,
        vessel_id: Optional[int] = None,
        ship_id: Optional[str] = None,
        event_date: Optional[date] = None,
        q: Optional[str] = None,
        is_accepted: Optional[bool] = None,
        vessel_type_id: Optional[int] = None,
        occurred_from: Optional[datetime] = None,
        occurred_to: Optional[datetime] = None,
        min_confidence: Optional[float] = None,
        sort: str = DEFAULT_SORT,
        order: str = DEFAULT_ORDER,
    ) -> int:
        """Tổng số bản ghi khớp bộ lọc (trước khi phân trang)."""
        return (
            self._filtered_query(
                db,
                vessel_id=vessel_id,
                ship_id=ship_id,
                event_date=event_date,
                q=q,
                is_accepted=is_accepted,
                vessel_type_id=vessel_type_id,
                occurred_from=occurred_from,
                occurred_to=occurred_to,
                min_confidence=min_confidence,
                sort=sort,
                order=order,
            )
            # Đếm không cần thứ tự (và bỏ luôn subquery camera nếu có).
            .order_by(None)
            .count()
        )

    def create(self, db: Session, data) -> Detection:
        payload = data.model_dump() if hasattr(data, 'model_dump') else dict(data)
        # Ensure vessel_id is present if not provided in data but available via vessel lookup
        db_obj = Detection(**payload)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update_acceptance(self, db: Session, detection_id: int, is_accepted: bool, verified_by: Optional[int] = None, rejection_reason: Optional[str] = None) -> Optional[Detection]:
        db_obj = self.get(db, detection_id)
        if not db_obj:
            return None
        db_obj.is_accepted = is_accepted
        db_obj.verified_at = datetime.now(timezone.utc)
        if verified_by:
            db_obj.verified_by = verified_by
        if not is_accepted and rejection_reason:
            db_obj.rejection_reason = rejection_reason
        db.commit()
        return self.get(db, detection_id)

    def update_vessel_id(
        self,
        db: Session,
        detection_id: int,
        vessel_id: int,
    ) -> Optional[Detection]:
        db_obj = self.get(db, detection_id)
        if not db_obj:
            return None
        db_obj.vessel_id = vessel_id
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update_fields(
        self,
        db: Session,
        detection_id: int,
        data: dict,
        *,
        commit: bool = True,
    ) -> Optional[Detection]:
        """Ghi field được phép sửa; caller có thể giữ transaction mở."""
        db_obj = self.get(db, detection_id)
        if not db_obj:
            return None
        editable = {
            'vessel_id',
            'track_id',
            'start_time',
            'end_time',
            'berth_in_time',
            'berth_out_time',
            'confidence',
        }
        for key, value in data.items():
            if key in editable:
                setattr(db_obj, key, value)
        if commit:
            db.commit()
        else:
            db.flush()
        db.refresh(db_obj)
        return self.get(db, detection_id)

    def delete(self, db: Session, detection_id: int) -> bool:
        db_obj = self.get(db, detection_id)
        if not db_obj:
            return False
        db.delete(db_obj)
        db.commit()
        return True

    def get_overlapping_by_vessel(
        self,
        db: Session,
        vessel_id: int,
        berth_in: datetime,
        berth_out: datetime,
        exclude_id: int,
        window_hours: float = 2.0,
    ) -> List[Detection]:
        from datetime import timedelta

        earliest = berth_in - timedelta(hours=float(window_hours))
        latest = berth_out + timedelta(hours=float(window_hours))
        # Candidate phải có berth_in; berth_out có thể NULL (track mất giữa
        # chừng) — absorb_contained dùng end_time fallback cho duration.
        return (
            db.query(Detection)
            .options(joinedload(Detection.invoices))
            .filter(
                Detection.vessel_id == vessel_id,
                Detection.id != exclude_id,
                Detection.deleted_at.is_(None),
                Detection.is_accepted.isnot(True),
                Detection.berth_in_time.isnot(None),
                Detection.berth_in_time >= earliest,
                Detection.berth_in_time <= latest,
            )
            .all()
        )

    def soft_delete(self, db: Session, detection_id: int) -> None:
        """Mark detection as deleted. Caller is responsible for committing."""
        db_obj = self.get(db, detection_id)
        if db_obj is None:
            return
        db_obj.deleted_at = datetime.now(timezone.utc)


detection_repo = DetectionRepository()
