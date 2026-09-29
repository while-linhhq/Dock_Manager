from sqlalchemy.orm import Query, Session
from sqlalchemy.orm import joinedload
from app.models.audit_log import AuditLog
from typing import List, Optional

# Hide read-only audit rows (legacy READ rows before middleware change)
_AUDIT_LIST_SKIP_ACTIONS = ('READ', 'HEAD', 'OPTIONS')


class AuditLogRepository:
    def create(self, db: Session, log_data: dict) -> AuditLog:
        db_log = AuditLog(**log_data)
        db.add(db_log)
        db.commit()
        db.refresh(db_log)
        return db_log

    def _filtered_query(self, db: Session, *, user_id: Optional[int] = None) -> Query:
        """Query đã áp bộ lọc, dùng chung cho `get_by_user` và `count_by_user`."""
        q = (
            db.query(AuditLog)
            .filter(~AuditLog.action.in_(_AUDIT_LIST_SKIP_ACTIONS))
        )
        if user_id is not None:
            q = q.filter(AuditLog.user_id == user_id)
        return q

    def get_by_user(
        self,
        db: Session,
        user_id: Optional[int] = None,
        limit: int = 100,
        skip: int = 0,
    ) -> List[AuditLog]:
        return (
            self._filtered_query(db, user_id=user_id)
            .options(joinedload(AuditLog.user))
            .order_by(AuditLog.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count_by_user(self, db: Session, *, user_id: Optional[int] = None) -> int:
        """Tổng số audit-log khớp bộ lọc (trước khi phân trang)."""
        return self._filtered_query(db, user_id=user_id).count()


audit_log_repo = AuditLogRepository()
