from datetime import date, datetime, timedelta
from sqlalchemy import func, or_
from sqlalchemy.orm import Query, Session
from app.models.port_log import PortLog
from app.models.vessel import Vessel
from app.utils.sql_filters import ilike_contains
from typing import List, Optional

DEFAULT_SORT = 'time'
DEFAULT_ORDER = 'desc'

# Whitelist cột sắp xếp: hai cột bấm sắp xếp được của bảng nhật ký cảng
# (`StatisticsLogsTable` — `time` = `portLogTimeIso`, `voted_ship_id`). `sort` của
# client chỉ được TRA CỨU ở đây, không bao giờ được nội suy thành tên cột.
SORT_COLUMNS = {
    'time': lambda: PortLog.logged_at,
    'voted_ship_id': lambda: PortLog.voted_ship_id,
}


class PortLogRepository:
    def get(self, db: Session, log_id: int) -> Optional[PortLog]:
        return db.query(PortLog).filter(PortLog.id == log_id).first()

    def _filtered_query(
        self,
        db: Session,
        *,
        ship_id: Optional[str] = None,
        log_date: Optional[date] = None,
        q: Optional[str] = None,
        vessel_type_id: Optional[int] = None,
        min_confidence: Optional[float] = None,
        logged_from: Optional[datetime] = None,
        logged_to: Optional[datetime] = None,
        sort: str = DEFAULT_SORT,
        order: str = DEFAULT_ORDER,
    ) -> Query:
        """Query đã áp bộ lọc + sắp xếp, dùng chung cho `get_all_logs` và `count_logs`.

        Nhờ dùng chung một chỗ dựng query, `X-Total-Count` luôn khớp đúng tập bản
        ghi mà danh sách trả về (kể cả khi bộ lọc đổi về sau).

        Bộ lọc port từ trang thống kê (`StatisticsView.tsx:34-61`), gồm 5 bộ lọc
        của trang: nhãn tàu (`q`), `vessel_type_id`, `track_id` (`q`),
        `logged_from`/`logged_to` và `min_confidence`; hai tham số cũ `ship_id`
        (khớp đúng `voted_ship_id`) và `log_date` (một ngày lịch của `logged_at`)
        giữ nguyên ngữ nghĩa.

        `q` tìm không phân biệt hoa thường trên đúng hai trường mà trang tìm:
        nhãn tàu hiển thị (`voted_ship_id`, port của `portLogShip`) và `track_id`;
        wildcard của LIKE trong `q` bị escape.

        `logged_from`/`logged_to` là instant UTC so với `logged_at` — cột
        `timestamp without time zone` chứa giờ UTC, nên ép `timezone('UTC', ...)`
        để không phụ thuộc timezone của session DB. Row thiếu `logged_at` bị loại
        khi có khoảng, đúng `isoInLocalDateRange(null)` của client.

        `vessel_type_id` tra loại tàu qua `vessels.ship_id = port_logs.voted_ship_id`
        (đúng `vessels.find(v => v.ship_id === sid)` của client; `vessels.ship_id`
        là unique nên join không nhân dòng).

        Mọi thứ tự đều kết thúc bằng `port_logs.id desc` làm tiebreaker để phân
        trang không trả trùng hoặc mất row khi nhiều row cùng khóa sắp xếp; giá
        trị rỗng luôn xuống cuối ở cả hai chiều, giống `sortRows` của client.
        """
        query = db.query(PortLog)
        joined_vessel = False

        def with_vessel(current: Query) -> Query:
            """JOIN `vessels` đúng một lần, kiểu outer để log của tàu lạ vẫn còn."""
            nonlocal joined_vessel
            if not joined_vessel:
                current = current.outerjoin(Vessel, Vessel.ship_id == PortLog.voted_ship_id)
                joined_vessel = True
            return current

        if ship_id:
            query = query.filter(PortLog.voted_ship_id == ship_id)
        if log_date:
            query = query.filter(
                PortLog.logged_at >= log_date,
                PortLog.logged_at < date.fromordinal(log_date.toordinal() + 1),
            )
        if q and q.strip():
            needle = q.strip()
            query = query.filter(
                or_(
                    ilike_contains(PortLog.voted_ship_id, needle),
                    ilike_contains(PortLog.track_id, needle),
                )
            )
        if vessel_type_id is not None:
            query = with_vessel(query).filter(Vessel.vessel_type_id == vessel_type_id)
        if min_confidence is not None:
            # Client coi confidence thiếu là 0 (`Number(log.confidence ?? 0)`).
            query = query.filter(func.coalesce(PortLog.confidence, 0.0) >= min_confidence)
        if logged_from is not None:
            query = query.filter(func.timezone('UTC', PortLog.logged_at) >= logged_from)
        if logged_to is not None:
            query = query.filter(func.timezone('UTC', PortLog.logged_at) <= logged_to)

        # --- Sắp xếp: `sort` lạ rơi về mặc định, không bao giờ vào SQL.
        key = (sort or '').strip().lower()
        column_factory = SORT_COLUMNS.get(key)
        if column_factory is None:
            key = DEFAULT_SORT
            column_factory = SORT_COLUMNS[DEFAULT_SORT]
        column = column_factory()

        ascending = (order or '').strip().lower() == 'asc'
        ordered = column.asc() if ascending else column.desc()
        return query.order_by(ordered.nullslast(), PortLog.id.desc())

    def get_all_logs(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        ship_id: Optional[str] = None,
        log_date: Optional[date] = None,
        q: Optional[str] = None,
        vessel_type_id: Optional[int] = None,
        min_confidence: Optional[float] = None,
        logged_from: Optional[datetime] = None,
        logged_to: Optional[datetime] = None,
        sort: str = DEFAULT_SORT,
        order: str = DEFAULT_ORDER,
    ) -> List[PortLog]:
        return (
            self._filtered_query(
                db,
                ship_id=ship_id,
                log_date=log_date,
                q=q,
                vessel_type_id=vessel_type_id,
                min_confidence=min_confidence,
                logged_from=logged_from,
                logged_to=logged_to,
                sort=sort,
                order=order,
            )
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count_logs(
        self,
        db: Session,
        *,
        ship_id: Optional[str] = None,
        log_date: Optional[date] = None,
        q: Optional[str] = None,
        vessel_type_id: Optional[int] = None,
        min_confidence: Optional[float] = None,
        logged_from: Optional[datetime] = None,
        logged_to: Optional[datetime] = None,
        sort: str = DEFAULT_SORT,
        order: str = DEFAULT_ORDER,
    ) -> int:
        """Tổng số port-log khớp bộ lọc (trước khi phân trang)."""
        return (
            self._filtered_query(
                db,
                ship_id=ship_id,
                log_date=log_date,
                q=q,
                vessel_type_id=vessel_type_id,
                min_confidence=min_confidence,
                logged_from=logged_from,
                logged_to=logged_to,
                sort=sort,
                order=order,
            )
            # Đếm không cần thứ tự.
            .order_by(None)
            .count()
        )

    def get_logs_by_date(self, db: Session, log_date: date) -> List[PortLog]:
        start = datetime.combine(log_date, datetime.min.time())
        end = start + timedelta(days=1)
        return db.query(PortLog).filter(PortLog.logged_at >= start, PortLog.logged_at < end).all()

    def create(self, db: Session, data) -> PortLog:
        payload = data.model_dump() if hasattr(data, 'model_dump') else dict(data)
        db_obj = PortLog(**payload)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def delete(self, db: Session, log_id: int) -> bool:
        db_obj = self.get(db, log_id)
        if not db_obj:
            return False
        db.delete(db_obj)
        db.commit()
        return True


port_log_repo = PortLogRepository()
