from datetime import datetime
from sqlalchemy import String, cast, func, or_
from sqlalchemy.orm import Query, Session
from sqlalchemy.orm import joinedload
from app.models.audit_log import AuditLog
from app.models.user import User
from app.utils.sql_filters import ilike_contains
from typing import List, Optional

# Hide read-only audit rows (legacy READ rows before middleware change)
_AUDIT_LIST_SKIP_ACTIONS = ('READ', 'HEAD', 'OPTIONS')

DEFAULT_SORT = 'created_at'
DEFAULT_ORDER = 'desc'

# Nhãn '—' của payload khi audit-log không gắn bản ghi nào (xem
# `AuditLogRead.fill_legacy_aliases`): client tìm kiếm trên chính chuỗi này.
MISSING_RECORD_ID = '—'
DEFAULT_TABLE_NAME = 'system'


def _table_name_expr():
    """`table_name` của payload: `entity_type` đã trim, thiếu thì 'system'."""
    return func.coalesce(func.nullif(func.trim(AuditLog.entity_type), ''), DEFAULT_TABLE_NAME)


def _record_id_expr():
    """`record_id` của payload: `str(entity_id)`, thiếu thì '—'."""
    return func.coalesce(cast(AuditLog.entity_id, String), MISSING_RECORD_ID)


# Whitelist cột sắp xếp: `sort` của client chỉ được TRA CỨU ở đây, không bao giờ
# được nội suy thành tên cột. Trang lịch sử không có tiêu đề bấm sắp xếp, nên đây
# là các cột hiển thị của nó (`created_at` là mặc định, giữ nguyên thứ tự cũ).
SORT_COLUMNS = {
    'created_at': lambda: AuditLog.created_at,
    'action': lambda: AuditLog.action,
    'table_name': _table_name_expr,
}


class AuditLogRepository:
    def create(self, db: Session, log_data: dict) -> AuditLog:
        db_log = AuditLog(**log_data)
        db.add(db_log)
        db.commit()
        db.refresh(db_log)
        return db_log

    def _filtered_query(
        self,
        db: Session,
        *,
        user_id: Optional[int] = None,
        q: Optional[str] = None,
        action: Optional[str] = None,
        table_name: Optional[str] = None,
        created_from: Optional[datetime] = None,
        created_to: Optional[datetime] = None,
        sort: str = DEFAULT_SORT,
        order: str = DEFAULT_ORDER,
    ) -> Query:
        """Query đã áp bộ lọc + sắp xếp, dùng chung cho `get_by_user` và `count_by_user`.

        Nhờ dùng chung một chỗ dựng query, `X-Total-Count` luôn khớp đúng tập bản
        ghi mà danh sách trả về (kể cả khi bộ lọc đổi về sau).

        Bộ lọc port từ trang lịch sử hệ thống (`BackupView.tsx:19-43`), gồm 4 bộ
        lọc của trang — `q`, `table_name`, `action`, `created_from`/`created_to` —
        bên cạnh tham số cũ `user_id`.

        `q` tìm không phân biệt hoa thường trên đúng 4 trường `matchesAnyField`
        của client: `action`, `record_id` (`str(entity_id)`, thiếu thì '—'),
        `user.full_name` và `user.email`; wildcard của LIKE trong `q` bị escape.
        `table_name` lọc chứa trên `entity_type` (đã trim, thiếu thì 'system') —
        đúng chuỗi payload mà client tìm; `action` lọc chứa trên `action`.

        `created_from`/`created_to` là instant UTC so với `audit_logs.created_at`.

        Các bộ lọc mới là điều kiện **độc lập** với `user_id` và với bộ lọc ẩn
        `_AUDIT_LIST_SKIP_ACTIONS` (READ/HEAD/OPTIONS không bao giờ lọt ra).

        Mọi thứ tự đều kết thúc bằng `audit_logs.id desc` làm tiebreaker để phân
        trang không trả trùng hoặc mất row khi nhiều row cùng khóa sắp xếp; giá
        trị rỗng luôn xuống cuối ở cả hai chiều, giống `sortRows` của client.
        """
        query = (
            db.query(AuditLog)
            .filter(~AuditLog.action.in_(_AUDIT_LIST_SKIP_ACTIONS))
        )
        joined_user = False

        def with_user(current: Query) -> Query:
            """JOIN `users` đúng một lần, kiểu outer để audit không có user vẫn còn."""
            nonlocal joined_user
            if not joined_user:
                current = current.outerjoin(User, AuditLog.user_id == User.id)
                joined_user = True
            return current

        if user_id is not None:
            query = query.filter(AuditLog.user_id == user_id)
        if q and q.strip():
            needle = q.strip()
            query = with_user(query).filter(
                or_(
                    ilike_contains(AuditLog.action, needle),
                    ilike_contains(_record_id_expr(), needle),
                    ilike_contains(User.full_name, needle),
                    ilike_contains(User.email, needle),
                )
            )
        if action and action.strip():
            query = query.filter(ilike_contains(AuditLog.action, action.strip()))
        if table_name and table_name.strip():
            query = query.filter(ilike_contains(_table_name_expr(), table_name.strip()))
        if created_from is not None:
            query = query.filter(AuditLog.created_at >= created_from)
        if created_to is not None:
            query = query.filter(AuditLog.created_at <= created_to)

        # --- Sắp xếp: `sort` lạ rơi về mặc định, không bao giờ vào SQL.
        key = (sort or '').strip().lower()
        column_factory = SORT_COLUMNS.get(key)
        if column_factory is None:
            key = DEFAULT_SORT
            column_factory = SORT_COLUMNS[DEFAULT_SORT]
        column = column_factory()

        ascending = (order or '').strip().lower() == 'asc'
        ordered = column.asc() if ascending else column.desc()
        return query.order_by(ordered.nullslast(), AuditLog.id.desc())

    def get_by_user(
        self,
        db: Session,
        user_id: Optional[int] = None,
        limit: int = 100,
        skip: int = 0,
        q: Optional[str] = None,
        action: Optional[str] = None,
        table_name: Optional[str] = None,
        created_from: Optional[datetime] = None,
        created_to: Optional[datetime] = None,
        sort: str = DEFAULT_SORT,
        order: str = DEFAULT_ORDER,
    ) -> List[AuditLog]:
        return (
            self._filtered_query(
                db,
                user_id=user_id,
                q=q,
                action=action,
                table_name=table_name,
                created_from=created_from,
                created_to=created_to,
                sort=sort,
                order=order,
            )
            .options(joinedload(AuditLog.user))
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count_by_user(
        self,
        db: Session,
        *,
        user_id: Optional[int] = None,
        q: Optional[str] = None,
        action: Optional[str] = None,
        table_name: Optional[str] = None,
        created_from: Optional[datetime] = None,
        created_to: Optional[datetime] = None,
        sort: str = DEFAULT_SORT,
        order: str = DEFAULT_ORDER,
    ) -> int:
        """Tổng số audit-log khớp bộ lọc (trước khi phân trang)."""
        return (
            self._filtered_query(
                db,
                user_id=user_id,
                q=q,
                action=action,
                table_name=table_name,
                created_from=created_from,
                created_to=created_to,
                sort=sort,
                order=order,
            )
            # Đếm không cần thứ tự.
            .order_by(None)
            .count()
        )


audit_log_repo = AuditLogRepository()
