from datetime import date
from sqlalchemy.orm import Session
from app.models.port_log import PortLog
from typing import List, Optional


class PortLogRepository:
    def get(self, db: Session, log_id: int) -> Optional[PortLog]:
        return db.query(PortLog).filter(PortLog.id == log_id).first()

    def get_all_logs(self, db: Session, skip: int = 0, limit: int = 100, ship_id: Optional[str] = None, log_date: Optional[date] = None) -> List[PortLog]:
        q = db.query(PortLog)
        if ship_id:
            q = q.filter(PortLog.voted_ship_id == ship_id)
        if log_date:
            q = q.filter(PortLog.logged_at >= log_date, PortLog.logged_at < date.fromordinal(log_date.toordinal() + 1))
        return q.order_by(PortLog.logged_at.desc()).offset(skip).limit(limit).all()

    def get_logs_by_date(self, db: Session, log_date: date) -> List[PortLog]:
        from datetime import datetime, timedelta
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
