from sqlalchemy.orm import Session
from app.models.export_log import ExportLog
from typing import List


class ExportLogRepository:
    def create(self, db: Session, log_data: dict) -> ExportLog:
        db_log = ExportLog(**log_data)
        db.add(db_log)
        db.commit()
        db.refresh(db_log)
        return db_log

    def get_all(self, db: Session, limit: int = 50) -> List[ExportLog]:
        return db.query(ExportLog).order_by(ExportLog.created_at.desc()).limit(limit).all()


export_log_repo = ExportLogRepository()
