from datetime import date, datetime, time, timedelta, timezone
from sqlalchemy import Date, String, and_, case, cast, func, or_, select, text
from sqlalchemy.orm import Query, Session, joinedload
from app.models.boundary_crossing_event import BoundaryCrossingEvent
from app.models.camera import Camera
from app.models.detection import Detection
from app.models.vessel import Vessel
from app.utils.sql_filters import ilike_contains
from typing import Dict, List, Optional, Tuple

# Nhãn hiển thị khi detection chưa gắn tàu và OCR không đọc được id nào — giữ
# đúng chuỗi client dùng trong `getDetectionShipLabel`.
UNKNOWN_SHIP_LABEL = 'KHÔNG XÁC ĐỊNH'

# Tập ký tự `String.trim()` của JS cắt (WhiteSpace + LineTerminator). `btrim` một
# tham số chỉ cắt khoảng trắng ASCII nên phải truyền tường minh tập này.
JS_TRIM_CHARS = (
    ' \t\n\v\f\r\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007'
    '\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff'
)

DEFAULT_SORT = 'berth'
DEFAULT_ORDER = 'desc'


def _js_trim(expr):
    """`String.trim()` của JS — cắt đúng bộ ký tự `JS_TRIM_CHARS` ở hai đầu."""
    return func.btrim(expr, JS_TRIM_CHARS)


def _ship_label_expr():
    """Nhãn tàu hiển thị, port từ `getDetectionShipLabel` của client.

    Ưu tiên `vessels.ship_id`, rồi id OCR đầu tiên, cuối cùng là nhãn "không xác
    định". Cả hai giá trị đều được trim như client nên id OCR toàn khoảng trắng
    rơi về nhãn mặc định chứ không thành nhãn trắng. Cần JOIN `vessels` kiểu outer.
    """
    return func.coalesce(
        func.nullif(_js_trim(Vessel.ship_id), ''),
        func.nullif(_js_trim(func.jsonb_extract_path_text(Detection.ocr_results, '0', 'id')), ''),
        UNKNOWN_SHIP_LABEL,
    )


def _berth_time_expr():
    """Instant tàu vào vùng neo đậu — port `getDetectionSortTs` của client.

    `berth_in_time` là `timestamp with time zone`, còn `start_time`/`created_at`
    là `timestamp without time zone` chứa giờ UTC: phải `timezone('UTC', ...)` để
    coalesce cùng kiểu và **không** phụ thuộc timezone của session DB.
    """
    # Giả định: `start_time`/`created_at` tuy là naive nhưng chứa giờ UTC, không
    # phải giờ local — nếu không, mốc sort này sẽ lệch so với `getDetectionSortTs`.
    return func.coalesce(
        Detection.berth_in_time,
        func.timezone('UTC', Detection.start_time),
        func.timezone('UTC', Detection.created_at),
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
# được nội suy thành tên cột. `berth` là mặc định vì đúng thứ tự client đang thấy
# (`getDetectionSortTs`); `time` là thời gian hiển thị của cột "Thời gian".
SORT_COLUMNS = {
    'berth': _berth_time_expr,
    'time': lambda: func.coalesce(Detection.start_time, Detection.created_at),
    'ship_id': _ship_label_expr,
    'confidence': lambda: func.coalesce(Detection.confidence, 0.0),
    'camera': _camera_in_name_expr,
    'status': _status_expr,
}

# Khóa sort cần JOIN `vessels` mới dựng được biểu thức.
VESSEL_JOIN_SORTS = frozenset({'ship_id'})


# --- Tổng hợp cho dashboard (Task 17) -------------------------------------
#
# Bốn widget phân tích của dashboard giờ đọc số tổng hợp từ SQL thay vì tự đếm
# trên 120 row mới nhất mà sidebar tải về. Mỗi hàm dưới đây là MỘT truy vấn
# GROUP BY; không hàm nào nạp row về Python để đếm.

# Số khung giờ của biểu đồ "24 giờ qua".
ANALYTICS_HOURS = 24

# Biên + nhãn ba bucket độ tin cậy. Nhãn PHẢI trùng từng ký tự với
# `buildConfidenceBuckets` của client
# (client/src/features/dashboard/utils/dashboard-analytics-data.ts):
# '< 50%' · '50–75%' (gạch ngang en-dash U+2013) · '≥ 75%' (U+2265).
CONFIDENCE_BUCKET_EDGES = (0.5, 0.75)
CONFIDENCE_BUCKET_LABELS = ('< 50%', '50–75%', '≥ 75%')

# Thứ tự cố định của donut trạng thái duyệt, khớp `buildAcceptanceSplit`:
# accepted = is_accepted TRUE ('Đã xác nhận'), rejected = FALSE ('Chưa xác nhận'),
# pending = NULL ('Chưa gán').
ACCEPTANCE_KEYS = ('accepted', 'rejected', 'pending')


def _period_window_filters(start: datetime, end: datetime) -> list:
    """Lọc chung của ba widget theo kỳ: chưa xoá mềm + `created_at` ∈ [start, end).

    Cố ý dùng ĐÚNG cách `/dashboard/summary` đang làm: lọc trên `created_at`,
    nửa khoảng mở, so trực tiếp với biên aware. `created_at` là `timestamp without
    time zone` chứa giờ UTC (xem `_berth_time_expr`) nên phép so này dựa vào
    TimeZone của session DB — đúng bằng UTC ở deployment hiện tại, và giữ nguyên
    con số của summary thay vì tự ý đổi ngữ nghĩa.
    """
    return [
        Detection.deleted_at.is_(None),
        Detection.created_at >= start,
        Detection.created_at < end,
    ]


def _ship_count_query(db: Session, start: datetime, end: datetime, limit: int) -> Query:
    """Query đếm theo nhãn tàu hiển thị — dùng chung cho `top_ship_counts`.

    Nhãn lấy từ `_ship_label_expr()` (port `getDetectionShipLabel` của client),
    KHÔNG phải `coalesce(vessels.ship_id, track_id)` mà `/dashboard/summary` dùng:
    widget này hiển thị nhãn của client nên phải khớp `buildTopShipCounts`.
    """
    label = _ship_label_expr()
    count = func.count(Detection.id)
    return (
        db.query(label.label('label'), count.label('count'))
        .select_from(Detection)
        .outerjoin(Vessel, Detection.vessel_id == Vessel.id)
        .filter(*_period_window_filters(start, end))
        .group_by(label)
        .order_by(count.desc(), label.asc())
        .limit(limit)
    )


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
        không trả trùng hoặc mất row khi nhiều row cùng khóa sắp xếp. Mặc định
        `berth` giữ đúng thứ tự client đang thấy (`getDetectionSortTs`); `time` là
        thời gian hiển thị và 5 khóa còn lại là 5 cột của bảng.
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

    def count_created_on(self, db: Session, day: date) -> int:
        """Số detection tạo trong ngày `day` — đếm bằng COUNT, không nạp row.

        Dùng chung `_filtered_query` nên vẫn loại row đã xoá mềm đúng như
        `get_all`. `cast(created_at, Date)` giữ nguyên ngữ nghĩa cũ
        `created_at.date() == date.today()`: row có `created_at IS NULL` cho NULL
        nên không được đếm, và không có quy đổi timezone nào ở đây.
        """
        return (
            self._filtered_query(db)
            .filter(cast(Detection.created_at, Date) == day)
            # Đếm không cần thứ tự.
            .order_by(None)
            .count()
        )

    def count_by_hour(
        self,
        db: Session,
        *,
        hours: int = ANALYTICS_HOURS,
        now: Optional[datetime] = None,
    ) -> List[Tuple[datetime, int]]:
        """Biểu đồ "24 giờ qua" — MỘT truy vấn, trả đủ `hours` bucket tăng dần.

        Port `buildDetectionsByHourLast24h` của client: mốc thời gian là
        `coalesce(start_time, created_at)` (hai cột naive chứa giờ UTC), bucket là
        giờ đã cắt phút. Cửa sổ CỐ ĐỊNH `hours` giờ gần nhất, khung giờ hiện tại là
        bucket cuối (có thể mới chạy được một phần) — đúng như biểu đồ mô tả và
        KHÔNG phụ thuộc `period`.

        Trục giờ sinh bằng `generate_series` rồi LEFT JOIN nên bucket rỗng vẫn có
        mặt với `count = 0`: biểu đồ luôn đủ 24 điểm, repository không phải đệm 0 ở
        Python. Trục để dạng naive-UTC và `date_trunc` cũng trên giá trị naive của
        row, nên phép so không kéo TimeZone của session DB vào; cột `hour` trả ra
        được gắn `timezone('UTC', ...)` để client nhận ISO-8601 UTC.

        Row đã xoá mềm bị loại. Row có cả `start_time` lẫn `created_at` NULL không
        khớp bucket nào nên không được đếm (client cũng bỏ qua row đó).

        `now` (chủ yếu để test) phải là instant; naive được coi là UTC cho khớp hai
        cột naive của DB.
        """
        moment = now or datetime.now(timezone.utc)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        anchor = moment.astimezone(timezone.utc).replace(
            minute=0, second=0, microsecond=0, tzinfo=None
        )
        start = anchor - timedelta(hours=max(int(hours), 1) - 1)
        # Trục giờ: một subquery sinh chuỗi giờ liên tiếp rồi LEFT JOIN sang
        # detections. `generate_series` trả về set nên subquery nở thành `hours`
        # dòng, và cột được đặt tên tường minh (`AS hour`).
        axis = select(
            func.generate_series(start, anchor, text("interval '1 hour'")).label('hour')
        ).subquery('hours')
        bucket = func.date_trunc(
            'hour', func.coalesce(Detection.start_time, Detection.created_at)
        )
        return (
            db.query(
                func.timezone('UTC', axis.c.hour).label('hour'),
                func.count(Detection.id).label('count'),
            )
            .select_from(axis)
            .outerjoin(
                Detection,
                and_(bucket == axis.c.hour, Detection.deleted_at.is_(None)),
            )
            .group_by(axis.c.hour)
            .order_by(axis.c.hour)
            .all()
        )

    def top_ship_counts(
        self,
        db: Session,
        *,
        start: datetime,
        end: datetime,
        limit: int = 8,
    ) -> List[Tuple[str, int]]:
        """Top nhãn tàu trong kỳ `[start, end)` — MỘT truy vấn GROUP BY, tối đa `limit`.

        Thứ tự: `count` giảm dần rồi tới nhãn tăng dần. Client cũ sắp chỉ theo
        `count` (Map giữ thứ tự chèn) nên khi bằng điểm thứ tự khác nhau; tiebreaker
        theo nhãn để kết quả ổn định giữa các lần gọi.
        """
        return _ship_count_query(db, start, end, limit).all()

    def acceptance_split(
        self, db: Session, *, start: datetime, end: datetime
    ) -> Dict[str, int]:
        """Đếm accepted/rejected/pending trong kỳ — MỘT truy vấn GROUP BY.

        Port `buildAcceptanceSplit`: accepted = `is_accepted IS TRUE`, rejected =
        `is_accepted IS FALSE`, pending = NULL (client gọi nhóm này là "Chưa gán" và
        xếp series theo đúng thứ tự `ACCEPTANCE_KEYS`).
        """
        key = case(
            (Detection.is_accepted.is_(True), 'accepted'),
            (Detection.is_accepted.is_(False), 'rejected'),
            else_='pending',
        )
        rows = (
            db.query(key.label('key'), func.count(Detection.id).label('count'))
            .select_from(Detection)
            .filter(*_period_window_filters(start, end))
            .group_by(key)
            .all()
        )
        # Nhóm vắng mặt trả 0 để donut luôn đủ ba lát.
        counts = {name: 0 for name in ACCEPTANCE_KEYS}
        for name, count in rows:
            counts[name] = int(count)
        return counts

    def confidence_bucket_counts(
        self, db: Session, *, start: datetime, end: datetime
    ) -> List[Tuple[str, int]]:
        """Ba bucket độ tin cậy trong kỳ — MỘT truy vấn GROUP BY.

        Port `buildConfidenceBuckets`: `conf < 0.5` · `0.5 ≤ conf < 0.75` ·
        `conf ≥ 0.75`, bỏ row `confidence IS NULL`. Trả đủ ba bucket theo đúng thứ
        tự nhãn của client, bucket rỗng = 0 (`CONFIDENCE_BUCKET_LABELS`).

        NaN cũng bị loại như client (`Number.isNaN` → `continue`): PostgreSQL coi
        NaN lớn hơn mọi số nên nếu không lọc, row NaN sẽ rơi nhầm vào bucket
        "≥ 75%"; `!= 'NaN'::float8` đúng vì NaN = NaN là TRUE trong PostgreSQL.
        """
        bucket = case(
            (
                Detection.confidence < CONFIDENCE_BUCKET_EDGES[0],
                CONFIDENCE_BUCKET_LABELS[0],
            ),
            (
                Detection.confidence < CONFIDENCE_BUCKET_EDGES[1],
                CONFIDENCE_BUCKET_LABELS[1],
            ),
            else_=CONFIDENCE_BUCKET_LABELS[2],
        )
        rows = (
            db.query(bucket.label('bucket'), func.count(Detection.id).label('count'))
            .select_from(Detection)
            .filter(
                *_period_window_filters(start, end),
                Detection.confidence.isnot(None),
                Detection.confidence != float('nan'),
            )
            .group_by(bucket)
            .all()
        )
        counts = {label: 0 for label in CONFIDENCE_BUCKET_LABELS}
        for label, count in rows:
            counts[label] = int(count)
        return [(label, counts[label]) for label in CONFIDENCE_BUCKET_LABELS]

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
