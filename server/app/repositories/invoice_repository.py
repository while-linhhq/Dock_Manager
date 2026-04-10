from sqlalchemy.orm import Session
from app.models.invoice import Invoice
from typing import List, Optional


class InvoiceRepository:
    def get(self, db: Session, invoice_id: int) -> Optional[Invoice]:
        return db.query(Invoice).filter(Invoice.id == invoice_id).first()

    def get_by_number(self, db: Session, invoice_number: str) -> Optional[Invoice]:
        return db.query(Invoice).filter(Invoice.invoice_number == invoice_number).first()

    def get_by_order(self, db: Session, order_id: int) -> List[Invoice]:
        return db.query(Invoice).filter(Invoice.order_id == order_id).all()

    def get_all(self, db: Session, skip: int = 0, limit: int = 100, payment_status: Optional[str] = None) -> List[Invoice]:
        q = db.query(Invoice)
        if payment_status:
            q = q.filter(Invoice.payment_status == payment_status)
        return q.order_by(Invoice.created_at.desc()).offset(skip).limit(limit).all()

    def count_unpaid(self, db: Session) -> int:
        return db.query(Invoice).filter(Invoice.payment_status == 'UNPAID').count()

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
            if value is not None:
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
        db_obj = self.get(db, invoice_id)
        if not db_obj:
            return False
        # payments FK is RESTRICT — remove payments before invoice
        for payment in list(db_obj.payments):
            db.delete(payment)
        db.delete(db_obj)
        db.commit()
        return True


invoice_repo = InvoiceRepository()
