from sqlalchemy.orm import Session
from app.models.audit_log import AuditLog
from typing import List, Optional


class AuditLogRepository:
    def create(self, db: Session, log_data: dict) -> AuditLog:
        db_log = AuditLog(**log_data)
        db.add(db_log)
        db.commit()
        db.refresh(db_log)
        return db_log

    def get_by_user(self, db: Session, user_id: Optional[int] = None, limit: int = 100) -> List[AuditLog]:
        q = db.query(AuditLog)
        if user_id is not None:
            q = q.filter(AuditLog.user_id == user_id)
        return q.order_by(AuditLog.created_at.desc()).limit(limit).all()


audit_log_repo = AuditLogRepository()
