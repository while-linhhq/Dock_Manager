import secrets
from datetime import datetime, timezone
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload
from app.models.order import Order
from typing import List, Optional

_ORDER_CREATE_KEYS = frozenset({
    'order_number',
    'vessel_id',
    'description',
    'status',
    'notes',
    'created_by',
    'total_amount',
})


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

    def get_all(self, db: Session, skip: int = 0, limit: int = 100, status: Optional[str] = None) -> List[Order]:
        q = db.query(Order).options(joinedload(Order.vessel))
        if status:
            q = q.filter(Order.status == status)
        return q.order_by(Order.created_at.desc()).offset(skip).limit(limit).all()

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
