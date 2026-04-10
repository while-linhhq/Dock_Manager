from datetime import datetime
from sqlalchemy.orm import Session
from app.models.order import Order
from typing import List, Optional


class OrderRepository:
    def get(self, db: Session, order_id: int) -> Optional[Order]:
        return db.query(Order).filter(Order.id == order_id).first()

    def get_by_number(self, db: Session, order_number: str) -> Optional[Order]:
        return db.query(Order).filter(Order.order_number == order_number).first()

    def get_all(self, db: Session, skip: int = 0, limit: int = 100, status: Optional[str] = None) -> List[Order]:
        q = db.query(Order)
        if status:
            q = q.filter(Order.status == status)
        return q.order_by(Order.created_at.desc()).offset(skip).limit(limit).all()

    def get_pending_by_vessel(self, db: Session, vessel_id: int) -> Optional[Order]:
        return db.query(Order).filter(
            Order.vessel_id == vessel_id,
            Order.status == 'PENDING',
        ).first()

    def create(self, db: Session, data) -> Order:
        payload = data.model_dump() if hasattr(data, 'model_dump') else dict(data)
        db_obj = Order(**payload)
        db.add(db_obj)
        db.commit()
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
        db_obj.completed_at = datetime.utcnow()
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
            db_obj.completed_at = datetime.utcnow()
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
