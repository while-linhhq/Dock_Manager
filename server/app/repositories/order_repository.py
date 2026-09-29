import secrets
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import String, case, cast, func, or_
from sqlalchemy.orm import Query, Session, joinedload
from app.models.order import Order
from app.models.vessel import Vessel
from app.utils.sql_filters import ilike_contains
from typing import List, Optional

DEFAULT_SORT = 'created_at'
DEFAULT_ORDER = 'desc'

# Đúng 4 trạng thái `normOrderStatus` của client nhận ra; giá trị khác rơi về
# 'pending' — cùng cách `statusLabels` chọn nhãn hiển thị.
_ORDER_STATUS_KEYS = ('processing', 'completed', 'pending', 'cancelled')

_ORDER_CREATE_KEYS = frozenset({
    'order_number',
    'vessel_id',
    'description',
    'status',
    'notes',
    'created_by',
    'total_amount',
})


def _status_expr():
    """Trạng thái đã chuẩn hoá — port `normOrderStatus` của client.

    `String(order.status ?? 'pending')` rồi `toLowerCase()`; giá trị lạ (kể cả
    NULL) rơi về 'pending'. Cột `status` không có CHECK nên phải làm đúng phép
    chuẩn hoá này thay vì tin vào dữ liệu.
    """
    lowered = func.lower(Order.status)
    return case((lowered.in_(_ORDER_STATUS_KEYS), lowered), else_='pending')


# Whitelist cột sắp xếp: khóa đúng bằng `sortAccessors` của `OrdersListSection`
# (`order_code`, `vessel`, `created_at`, `status`, `total_amount`). `sort` của
# client chỉ được TRA CỨU ở đây, không bao giờ được nội suy thành tên cột.
SORT_COLUMNS = {
    'order_code': lambda: Order.id,
    'vessel': lambda: Vessel.ship_id,
    'created_at': lambda: Order.created_at,
    'status': _status_expr,
    'total_amount': lambda: func.coalesce(Order.total_amount, 0),
}

# Khóa sort cần JOIN `vessels` mới dựng được biểu thức.
VESSEL_JOIN_SORTS = frozenset({'vessel'})


class OrderRepository:
    def get(self, db: Session, order_id: int) -> Optional[Order]:
        return (
            db.query(Order)
            .options(joinedload(Order.vessel))
            .filter(Order.id == order_id)
            .first()
        )

    def get_by_number(self, db: Session, order_number: str) -> Optional[Order]:
        return db.query(Order).filter(Order.order_number == order_number).first()

    def generate_unique_order_number(self, db: Session) -> str:
        for _ in range(16):
            cand = (
                f"ORD-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-"
                f"{secrets.token_hex(3).upper()}"
            )
            if self.get_by_number(db, cand) is None:
                return cand
        raise RuntimeError('Could not allocate unique order_number')

    def _filtered_query(
        self,
        db: Session,
        *,
        status: Optional[str] = None,
        q: Optional[str] = None,
        vessel_id: Optional[int] = None,
        vessel_type_id: Optional[int] = None,
        created_from: Optional[datetime] = None,
        created_to: Optional[datetime] = None,
        min_total: Optional[Decimal] = None,
        max_total: Optional[Decimal] = None,
        sort: str = DEFAULT_SORT,
        order: str = DEFAULT_ORDER,
    ) -> Query:
        """Query đã áp bộ lọc + sắp xếp, dùng chung cho `get_all` và `count_filtered`.

        Nhờ dùng chung một chỗ dựng query, `X-Total-Count` luôn khớp đúng tập bản
        ghi mà danh sách trả về (kể cả khi bộ lọc đổi về sau).

        Bộ lọc port từ trang đơn hàng (`OrdersView.tsx:40-80`), gồm 8 bộ lọc:
        `q`, `status`, `vessel_id`, `vessel_type_id`, `created_from`,
        `created_to`, `min_total`, `max_total`.

        `q` tìm không phân biệt hoa thường trên đúng 4 trường `matchesAnyField`
        của client: id đơn (cast sang text), `vessels.ship_id`, `vessels.name` và
        mô tả hàng hoá; wildcard của LIKE trong `q` bị escape. `status` nhận cả
        chữ hoa/thường/`processing` qua `normalize_order_status` như trước.

        `created_from`/`created_to` là instant UTC so với `orders.created_at`
        (`timestamp with time zone`); `min_total`/`max_total` so trên
        `coalesce(total_amount, 0)` — client coi số tiền thiếu là 0.

        Mọi thứ tự đều kết thúc bằng `orders.id desc` làm tiebreaker để phân trang
        không trả trùng hoặc mất row khi nhiều row cùng khóa sắp xếp; giá trị rỗng
        luôn xuống cuối ở cả hai chiều, giống `sortRows` của client.
        """
        query = db.query(Order)
        joined_vessel = False

        def with_vessel(current: Query) -> Query:
            """JOIN `vessels` đúng một lần, kiểu outer để đơn chưa gắn tàu vẫn còn."""
            nonlocal joined_vessel
            if not joined_vessel:
                current = current.outerjoin(Vessel, Order.vessel_id == Vessel.id)
                joined_vessel = True
            return current

        if status:
            query = query.filter(Order.status == status)
        if q and q.strip():
            needle = q.strip()
            query = with_vessel(query).filter(
                or_(
                    ilike_contains(cast(Order.id, String), needle),
                    ilike_contains(Vessel.ship_id, needle),
                    ilike_contains(Vessel.name, needle),
                    ilike_contains(Order.description, needle),
                )
            )
        if vessel_id is not None:
            query = query.filter(Order.vessel_id == vessel_id)
        if vessel_type_id is not None:
            # Client tra loại tàu qua `vessels.find(v => v.id === order.vessel_id)`.
            query = with_vessel(query).filter(Vessel.vessel_type_id == vessel_type_id)
        if created_from is not None:
            query = query.filter(Order.created_at >= created_from)
        if created_to is not None:
            query = query.filter(Order.created_at <= created_to)
        if min_total is not None:
            query = query.filter(func.coalesce(Order.total_amount, 0) >= min_total)
        if max_total is not None:
            query = query.filter(func.coalesce(Order.total_amount, 0) <= max_total)

        # --- Sắp xếp: `sort` lạ rơi về mặc định, không bao giờ vào SQL.
        key = (sort or '').strip().lower()
        column_factory = SORT_COLUMNS.get(key)
        if column_factory is None:
            key = DEFAULT_SORT
            column_factory = SORT_COLUMNS[DEFAULT_SORT]
        if key in VESSEL_JOIN_SORTS:
            query = with_vessel(query)
        column = column_factory()

        ascending = (order or '').strip().lower() == 'asc'
        ordered = column.asc() if ascending else column.desc()
        return query.order_by(ordered.nullslast(), Order.id.desc())

    def get_all(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        status: Optional[str] = None,
        q: Optional[str] = None,
        vessel_id: Optional[int] = None,
        vessel_type_id: Optional[int] = None,
        created_from: Optional[datetime] = None,
        created_to: Optional[datetime] = None,
        min_total: Optional[Decimal] = None,
        max_total: Optional[Decimal] = None,
        sort: str = DEFAULT_SORT,
        order: str = DEFAULT_ORDER,
    ) -> List[Order]:
        return (
            self._filtered_query(
                db,
                status=status,
                q=q,
                vessel_id=vessel_id,
                vessel_type_id=vessel_type_id,
                created_from=created_from,
                created_to=created_to,
                min_total=min_total,
                max_total=max_total,
                sort=sort,
                order=order,
            )
            .options(joinedload(Order.vessel))
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count_filtered(
        self,
        db: Session,
        *,
        status: Optional[str] = None,
        q: Optional[str] = None,
        vessel_id: Optional[int] = None,
        vessel_type_id: Optional[int] = None,
        created_from: Optional[datetime] = None,
        created_to: Optional[datetime] = None,
        min_total: Optional[Decimal] = None,
        max_total: Optional[Decimal] = None,
        sort: str = DEFAULT_SORT,
        order: str = DEFAULT_ORDER,
    ) -> int:
        """Tổng số đơn khớp bộ lọc (trước khi phân trang)."""
        return (
            self._filtered_query(
                db,
                status=status,
                q=q,
                vessel_id=vessel_id,
                vessel_type_id=vessel_type_id,
                created_from=created_from,
                created_to=created_to,
                min_total=min_total,
                max_total=max_total,
                sort=sort,
                order=order,
            )
            # Đếm không cần thứ tự.
            .order_by(None)
            .count()
        )

    def count_by_status(self, db: Session, status: str) -> int:
        return int(
            db.query(func.count(Order.id)).filter(Order.status == status).scalar() or 0
        )

    def get_pending_by_vessel(self, db: Session, vessel_id: int) -> Optional[Order]:
        return db.query(Order).filter(
            Order.vessel_id == vessel_id,
            Order.status == 'PENDING',
        ).first()

    def create(self, db: Session, data, *, commit: bool = True) -> Order:
        payload = data.model_dump() if hasattr(data, 'model_dump') else dict(data)
        payload = {k: v for k, v in payload.items() if k in _ORDER_CREATE_KEYS}
        db_obj = Order(**payload)
        db.add(db_obj)
        if commit:
            db.commit()
        else:
            db.flush()
        db.refresh(db_obj)
        return db_obj

    def update(self, db: Session, order_id: int, data: dict) -> Optional[Order]:
        db_obj = self.get(db, order_id)
        if not db_obj:
            return None
        for key, value in data.items():
            if value is not None:
                setattr(db_obj, key, value)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def complete_order(self, db: Session, order_id: int) -> Optional[Order]:
        db_obj = self.get(db, order_id)
        if not db_obj:
            return None
        db_obj.status = 'COMPLETED'
        db_obj.completed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update_status(self, db: Session, order_id: int, status: str, updated_by: Optional[int] = None) -> Optional[Order]:
        db_obj = self.get(db, order_id)
        if not db_obj:
            return None
        db_obj.status = status
        if updated_by:
            db_obj.updated_by = updated_by
        if status == 'COMPLETED':
            db_obj.completed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def delete(self, db: Session, order_id: int) -> bool:
        db_obj = self.get(db, order_id)
        if not db_obj:
            return False
        db.delete(db_obj)
        db.commit()
        return True


order_repo = OrderRepository()
