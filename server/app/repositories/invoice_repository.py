import secrets
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Float, Numeric, String, case, cast, extract, func, or_
from sqlalchemy.orm import Query, Session, joinedload

from app.models.detection import Detection
from app.models.invoice import Invoice
from app.services.invoice_snapshot_service import seal_invoice_on_paid
from app.models.invoice_item import InvoiceItem
from app.models.payment import Payment
from app.models.user import User
from app.models.vessel import Vessel
from app.utils.sql_filters import ilike_contains
from typing import List, Optional

DEFAULT_SORT = 'time'
DEFAULT_ORDER = 'desc'

SECONDS_PER_MINUTE = 60


def _created_by_label_expr():
    """Nhãn người tạo, port từ `InvoiceRead.fill_created_by_label`.

    Hoá đơn AI luôn hiển thị 'AI'; còn lại lấy full_name → email → username → id,
    và '—' khi không có người tạo. Client tìm kiếm trên chính nhãn này
    (`inv.created_by_label`), nên SQL phải dựng đúng chuỗi đó. `trim()` của
    PostgreSQL chỉ cắt khoảng trắng ASCII, còn `String.trim()` của client rộng hơn.
    """
    return case(
        (func.upper(func.coalesce(Invoice.creation_source, 'USER')) == 'AI', 'AI'),
        (Invoice.created_by.is_(None), '—'),
        else_=func.coalesce(
            func.nullif(func.trim(User.full_name), ''),
            func.nullif(func.trim(User.email), ''),
            func.nullif(func.trim(User.username), ''),
            cast(User.id, String),
        ),
    )


def _vessel_ship_id_expr():
    """`vessel_ship_id` của payload: snapshot thắng, thiếu thì lấy `vessels.ship_id`."""
    return func.coalesce(func.nullif(Invoice.vessel_ship_id_snapshot, ''), Vessel.ship_id)


def _berth_minutes_expr():
    """Số phút neo, port từ `getInvoiceBerthMinutes` của client.

    Client nhận `berth_duration_seconds` = `round((end_time - start_time).total_seconds())`
    (validator `InvoiceRead.fill_created_by_label`) rồi chia 60; ở đây làm đúng phép
    tính đó trong SQL. Không có detection, thiếu `start_time`/`end_time`, hoặc số giây
    đã làm tròn <= 0 → NULL, đúng như client trả `null` (row luôn bị loại khi có ngưỡng).

    Khác biệt đã biết: `round()` của PostgreSQL làm tròn nửa lên còn `round()` của
    Python làm tròn nửa về số chẵn — chỉ lệch khi khoảng thời gian có đúng .5 giây.

    Phép chia và phép so phải chạy ở `double precision` (float8): client chia
    `totalSeconds / 60` bằng số thực double rồi so với ngưỡng cũng là double. Nếu để
    `numeric` (mặc định khi chia `numeric` cho 60), PostgreSQL sẽ so `numeric` với
    tham số float8 ở dạng `numeric` chính xác — 184/60 = 3.06666666666666666667
    trong khi double gần nhất là 3.066666666666667 — và loại oan row đúng bằng ngưỡng.
    """
    seconds = extract('epoch', Detection.end_time - Detection.start_time)
    rounded_seconds = func.round(cast(seconds, Numeric))
    # Client chỉ nhận số giây đã làm tròn và bỏ qua giá trị <= 0 (`berth_duration_seconds`).
    positive_seconds = case((rounded_seconds > 0, rounded_seconds), else_=None)
    return cast(positive_seconds, Float) / SECONDS_PER_MINUTE


def _ship_order_expr(ai_tab: bool):
    """Cột "tàu / đơn" của bảng: tab AI hiển thị ship_id, tab thường hiển thị order_id."""
    return _vessel_ship_id_expr() if ai_tab else Invoice.order_id


# Whitelist cột sắp xếp: `sort` của client chỉ được TRA CỨU ở đây, không bao giờ
# được nội suy thành tên cột. `time` (mặc định) = cột thời gian của chế độ hiện tại.
SORT_COLUMNS = {
    'invoice_number': lambda ai_tab: Invoice.invoice_number,
    'ship_order': _ship_order_expr,
    'created_at': lambda ai_tab: Invoice.created_at,
    'deleted_at': lambda ai_tab: Invoice.deleted_at,
    # CHECK `chk_invoices_payment_status` chỉ cho 5 giá trị viết hoa, nên `lower()`
    # đúng bằng `normInvoicePaymentStatus` mà client dùng để sắp xếp cột này.
    'payment_status': lambda ai_tab: func.lower(Invoice.payment_status),
    'total_amount': lambda ai_tab: func.coalesce(Invoice.total_amount, 0),
}


class InvoiceRepository:
    @staticmethod
    def _normalize_source(value: Optional[str]) -> str:
        return (value or '').strip().upper()

    def get(self, db: Session, invoice_id: int, include_deleted: bool = False) -> Optional[Invoice]:
        q = (
            db.query(Invoice)
            .options(
                joinedload(Invoice.creator),
                joinedload(Invoice.items).joinedload(InvoiceItem.fee_config),
                joinedload(Invoice.vessel).joinedload(Vessel.vessel_type),
                joinedload(Invoice.detection),
                joinedload(Invoice.discount_reviewer),
            )
            .filter(Invoice.id == invoice_id)
        )
        if not include_deleted:
            q = q.filter(Invoice.deleted_at.is_(None))
        return q.first()

    def get_by_number(self, db: Session, invoice_number: str) -> Optional[Invoice]:
        return (
            db.query(Invoice)
            .filter(Invoice.invoice_number == invoice_number)
            .filter(Invoice.deleted_at.is_(None))
            .first()
        )

    def generate_unique_invoice_number(self, db: Session) -> str:
        for _ in range(16):
            cand = f"INV-{datetime.now(timezone.utc).strftime('%y%m%d')}-{secrets.token_hex(3).upper()}"
            if self.get_by_number(db, cand) is None:
                return cand
        raise RuntimeError('Could not allocate unique invoice_number')

    def get_by_order(self, db: Session, order_id: int) -> List[Invoice]:
        return (
            db.query(Invoice)
            .filter(Invoice.order_id == order_id)
            .filter(Invoice.deleted_at.is_(None))
            .all()
        )

    def get_by_ids(self, db: Session, invoice_ids: List[int], *, include_deleted: bool = False) -> List[Invoice]:
        if not invoice_ids:
            return []
        q = (
            db.query(Invoice)
            .options(
                joinedload(Invoice.creator),
                joinedload(Invoice.items).joinedload(InvoiceItem.fee_config),
                joinedload(Invoice.vessel).joinedload(Vessel.vessel_type),
                joinedload(Invoice.detection),
            )
            .filter(Invoice.id.in_(invoice_ids))
        )
        if not include_deleted:
            q = q.filter(Invoice.deleted_at.is_(None))
        rows = q.all()
        order = {iid: idx for idx, iid in enumerate(invoice_ids)}
        rows.sort(key=lambda inv: order.get(inv.id, 10**9))
        return rows

    def get_by_detection_id(self, db: Session, detection_id: int) -> Optional[Invoice]:
        return (
            db.query(Invoice)
            .filter(Invoice.detection_id == detection_id)
            .filter(Invoice.deleted_at.is_(None))
            .first()
        )

    def _filtered_query(
        self,
        db: Session,
        *,
        payment_status: Optional[str] = None,
        awaiting_payment: Optional[bool] = None,
        deleted_only: bool = False,
        creation_source: Optional[str] = None,
        exclude_creation_source: Optional[str] = None,
        discount_status: Optional[str] = None,
        q: Optional[str] = None,
        vessel_id: Optional[int] = None,
        vessel_type_id: Optional[int] = None,
        created_from: Optional[datetime] = None,
        created_to: Optional[datetime] = None,
        min_total: Optional[Decimal] = None,
        max_total: Optional[Decimal] = None,
        min_berth_minutes: Optional[float] = None,
        sort: str = DEFAULT_SORT,
        order: str = DEFAULT_ORDER,
    ) -> Query:
        """Query đã áp bộ lọc và thứ tự, dùng chung cho danh sách và phép đếm.

        Nhờ dùng chung một chỗ dựng query, `X-Total-Count` luôn khớp đúng tập
        bản ghi mà danh sách trả về (kể cả khi bộ lọc đổi về sau).

        Bộ lọc port từ trang thu nhập (`RevenueView.tsx:168-225`), gồm 8 bộ lọc:
        `q`, `vessel_id`, `vessel_type_id`, `created_from`, `created_to`,
        `min_total`, `max_total`, `min_berth_minutes`. Chúng là điều kiện **độc
        lập**: áp dụng trong mọi chế độ (`deleted_only`, `payment_status`,
        `awaiting_payment`, `discount_status`, nguồn tạo) chứ không nằm trong
        chuỗi if/elif chọn chế độ.

        `created_from`/`created_to` là instant UTC so với `Invoice.created_at`.
        `q` tìm không phân biệt hoa thường trên số hoá đơn, order/vessel/detection
        id, ship_id (snapshot thắng) và nhãn người tạo; wildcard của LIKE trong
        `q` bị escape.

        Mọi thứ tự đều kết thúc bằng `invoices.id desc` làm tiebreaker để phân
        trang không trả trùng hoặc mất row khi nhiều row cùng khóa sắp xếp; giá
        trị rỗng luôn xuống cuối ở cả hai chiều, giống `sortRows` của client.
        """
        query = db.query(Invoice)
        joined_vessel = False
        joined_creator = False
        joined_detection = False

        def with_vessel(current: Query) -> Query:
            """JOIN `vessels` đúng một lần, kiểu outer để không mất row chưa gắn tàu."""
            nonlocal joined_vessel
            if not joined_vessel:
                current = current.outerjoin(Vessel, Invoice.vessel_id == Vessel.id)
                joined_vessel = True
            return current

        def with_creator(current: Query) -> Query:
            """JOIN `users` đúng một lần, kiểu outer để hoá đơn AI (không người tạo) vẫn còn."""
            nonlocal joined_creator
            if not joined_creator:
                current = current.outerjoin(User, Invoice.created_by == User.id)
                joined_creator = True
            return current

        def with_detection(current: Query) -> Query:
            """JOIN `detections` đúng một lần, kiểu outer để hoá đơn không có detection vẫn còn."""
            nonlocal joined_detection
            if not joined_detection:
                current = current.outerjoin(Detection, Invoice.detection_id == Detection.id)
                joined_detection = True
            return current

        # --- Chế độ (giữ nguyên hành vi cũ): chọn tập row + cột thời gian mặc định.
        if discount_status is not None:
            # Chế độ riêng của `/discount-requests`: giữ nguyên bộ lọc và thứ tự
            # `updated_at desc` như bản cũ. Chuẩn hoá ngay tại đây để
            # `get_by_discount_status` và `count_filtered` không bao giờ lệch nhau
            # vì một bên quên normalize.
            normalized_discount = (discount_status or 'pending').strip().lower()
            query = query.filter(Invoice.deleted_at.is_(None))
            query = query.filter(Invoice.discount_status == normalized_discount)
            default_order_column = Invoice.updated_at
        elif deleted_only:
            query = query.filter(Invoice.deleted_at.isnot(None))
            default_order_column = Invoice.deleted_at
        else:
            query = query.filter(Invoice.deleted_at.is_(None))
            if awaiting_payment is True:
                query = query.filter(Invoice.payment_status != 'PAID')
            elif payment_status:
                query = query.filter(Invoice.payment_status == payment_status)
            default_order_column = Invoice.created_at

        normalized_source = self._normalize_source(creation_source)
        if creation_source:
            if normalized_source == 'AI':
                # Backward-compatible: dữ liệu cũ từng dùng ORDER_AUTO cho hóa đơn tự động.
                query = query.filter(
                    or_(
                        Invoice.creation_source == 'AI',
                        Invoice.creation_source == 'ORDER_AUTO',
                    )
                )
            else:
                query = query.filter(Invoice.creation_source == normalized_source)
        elif exclude_creation_source:
            normalized_exclude = self._normalize_source(exclude_creation_source)
            query = query.filter(
                or_(
                    Invoice.creation_source.is_(None),
                    Invoice.creation_source != normalized_exclude,
                )
            )

        # --- 8 bộ lọc của trang thu nhập: điều kiện độc lập, áp cho mọi chế độ ở trên.
        if q and q.strip():
            # Cùng 6 trường client đưa vào `matchesAnyField` (`RevenueView.tsx:174-182`).
            needle = q.strip()
            query = with_creator(with_vessel(query)).filter(
                or_(
                    ilike_contains(Invoice.invoice_number, needle),
                    ilike_contains(cast(Invoice.order_id, String), needle),
                    ilike_contains(cast(Invoice.vessel_id, String), needle),
                    ilike_contains(cast(Invoice.detection_id, String), needle),
                    ilike_contains(_vessel_ship_id_expr(), needle),
                    ilike_contains(_created_by_label_expr(), needle),
                )
            )
        if vessel_id is not None:
            query = query.filter(Invoice.vessel_id == vessel_id)
        if vessel_type_id is not None:
            # Client tra loại tàu qua `filterVessels` theo `vessel_id` của hoá đơn.
            query = with_vessel(query).filter(Vessel.vessel_type_id == vessel_type_id)
        if created_from is not None:
            query = query.filter(Invoice.created_at >= created_from)
        if created_to is not None:
            query = query.filter(Invoice.created_at <= created_to)
        if min_total is not None:
            # Client coi tổng tiền thiếu là 0 (`inv.total_amount ?? 0`).
            query = query.filter(func.coalesce(Invoice.total_amount, 0) >= min_total)
        if max_total is not None:
            query = query.filter(func.coalesce(Invoice.total_amount, 0) <= max_total)
        if min_berth_minutes is not None:
            # `0` vẫn là một ngưỡng: hoá đơn không có số phút neo bị loại, khác
            # hẳn "không truyền tham số".
            query = with_detection(query).filter(
                _berth_minutes_expr() >= min_berth_minutes
            )

        # --- Sắp xếp: `sort` lạ rơi về mặc định, không bao giờ vào SQL.
        ai_tab = normalized_source == 'AI'
        key = (sort or '').strip().lower()
        if key not in SORT_COLUMNS:
            key = DEFAULT_SORT
        if key == DEFAULT_SORT:
            column = default_order_column
        else:
            if key == 'ship_order' and ai_tab:
                query = with_vessel(query)
            column = SORT_COLUMNS[key](ai_tab)

        ascending = (order or '').strip().lower() == 'asc'
        ordered = column.asc() if ascending else column.desc()
        return query.order_by(ordered.nullslast(), Invoice.id.desc())

    def count_filtered(
        self,
        db: Session,
        *,
        payment_status: Optional[str] = None,
        awaiting_payment: Optional[bool] = None,
        deleted_only: bool = False,
        creation_source: Optional[str] = None,
        exclude_creation_source: Optional[str] = None,
        discount_status: Optional[str] = None,
        q: Optional[str] = None,
        vessel_id: Optional[int] = None,
        vessel_type_id: Optional[int] = None,
        created_from: Optional[datetime] = None,
        created_to: Optional[datetime] = None,
        min_total: Optional[Decimal] = None,
        max_total: Optional[Decimal] = None,
        min_berth_minutes: Optional[float] = None,
        sort: str = DEFAULT_SORT,
        order: str = DEFAULT_ORDER,
    ) -> int:
        """Tổng số bản ghi khớp bộ lọc (trước khi phân trang)."""
        return (
            self._filtered_query(
                db,
                payment_status=payment_status,
                awaiting_payment=awaiting_payment,
                deleted_only=deleted_only,
                creation_source=creation_source,
                exclude_creation_source=exclude_creation_source,
                discount_status=discount_status,
                q=q,
                vessel_id=vessel_id,
                vessel_type_id=vessel_type_id,
                created_from=created_from,
                created_to=created_to,
                min_total=min_total,
                max_total=max_total,
                min_berth_minutes=min_berth_minutes,
                sort=sort,
                order=order,
            )
            # Đếm không cần thứ tự.
            .order_by(None)
            .count()
        )

    def get_all(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        payment_status: Optional[str] = None,
        awaiting_payment: Optional[bool] = None,
        deleted_only: bool = False,
        creation_source: Optional[str] = None,
        exclude_creation_source: Optional[str] = None,
        q: Optional[str] = None,
        vessel_id: Optional[int] = None,
        vessel_type_id: Optional[int] = None,
        created_from: Optional[datetime] = None,
        created_to: Optional[datetime] = None,
        min_total: Optional[Decimal] = None,
        max_total: Optional[Decimal] = None,
        min_berth_minutes: Optional[float] = None,
        sort: str = DEFAULT_SORT,
        order: str = DEFAULT_ORDER,
    ) -> List[Invoice]:
        return (
            self._filtered_query(
                db,
                payment_status=payment_status,
                awaiting_payment=awaiting_payment,
                deleted_only=deleted_only,
                creation_source=creation_source,
                exclude_creation_source=exclude_creation_source,
                q=q,
                vessel_id=vessel_id,
                vessel_type_id=vessel_type_id,
                created_from=created_from,
                created_to=created_to,
                min_total=min_total,
                max_total=max_total,
                min_berth_minutes=min_berth_minutes,
                sort=sort,
                order=order,
            )
            .options(
                joinedload(Invoice.creator),
                joinedload(Invoice.items).joinedload(InvoiceItem.fee_config),
                joinedload(Invoice.vessel).joinedload(Vessel.vessel_type),
                joinedload(Invoice.detection),
            )
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_by_discount_status(
        self,
        db: Session,
        status: str,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Invoice]:
        return (
            self._filtered_query(db, discount_status=status)
            .options(
                joinedload(Invoice.creator),
                joinedload(Invoice.discount_reviewer),
                joinedload(Invoice.items).joinedload(InvoiceItem.fee_config),
                joinedload(Invoice.vessel).joinedload(Vessel.vessel_type),
                joinedload(Invoice.detection),
            )
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_all_revenue_export(self, db: Session) -> List[Invoice]:
        """Mọi hóa đơn quản lý thu nhập: tạo tay + AI, mọi trạng thái, kể cả đã xóa."""
        return (
            db.query(Invoice)
            .options(
                joinedload(Invoice.creator),
                joinedload(Invoice.items).joinedload(InvoiceItem.fee_config),
                joinedload(Invoice.vessel).joinedload(Vessel.vessel_type),
                joinedload(Invoice.detection),
            )
            .order_by(Invoice.created_at.desc())
            .all()
        )

    def count_all_revenue_export(self, db: Session) -> int:
        return db.query(Invoice).count()

    def recalculate_payment_status(self, db: Session, invoice_id: int) -> None:
        """Cập nhật payment_status / paid_at theo tổng payments (sau POST payment)."""
        inv = (
            db.query(Invoice)
            .filter(Invoice.id == invoice_id, Invoice.deleted_at.is_(None))
            .first()
        )
        if not inv:
            return
        raw = (
            db.query(func.coalesce(func.sum(Payment.amount), 0))
            .filter(Payment.invoice_id == invoice_id)
            .scalar()
        )
        paid = Decimal(str(raw or 0)).quantize(Decimal('0.01'))
        total = (inv.total_amount or Decimal('0')).quantize(Decimal('0.01'))
        if total <= 0:
            new_status = 'PAID' if paid > 0 else 'UNPAID'
        elif paid >= total:
            new_status = 'PAID'
        elif paid > 0:
            new_status = 'PARTIAL'
        else:
            new_status = 'UNPAID'
        inv.payment_status = new_status
        if new_status == 'PAID':
            inv.paid_at = datetime.now(timezone.utc)
            seal_invoice_on_paid(db, inv)
        db.flush()

    def count_unpaid(self, db: Session) -> int:
        return (
            db.query(Invoice)
            .filter(Invoice.payment_status == 'UNPAID')
            .filter(Invoice.deleted_at.is_(None))
            .count()
        )

    def create(self, db: Session, data: dict) -> Invoice:
        db_obj = Invoice(**data)
        db.add(db_obj)
        db.flush()  # get id before commit for items
        db.refresh(db_obj)
        return db_obj

    def update(self, db: Session, invoice_id: int, data: dict) -> Optional[Invoice]:
        db_obj = self.get(db, invoice_id)
        if not db_obj:
            return None
        for key, value in data.items():
            if value is not None or key == 'notes':
                setattr(db_obj, key, value)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update_payment_status(self, db: Session, invoice_id: int, status: str) -> Optional[Invoice]:
        db_obj = self.get(db, invoice_id)
        if not db_obj:
            return None
        db_obj.payment_status = status
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def delete(self, db: Session, invoice_id: int) -> bool:
        """Soft-delete: sets deleted_at. Payments and rows are kept for audit."""
        db_obj = self.get(db, invoice_id, include_deleted=False)
        if not db_obj:
            return False
        db_obj.deleted_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(db_obj)
        return True


invoice_repo = InvoiceRepository()
