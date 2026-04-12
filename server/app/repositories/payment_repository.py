from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.payment import Payment
from app.repositories.invoice_repository import invoice_repo
from typing import List, Optional


class PaymentRepository:
    def get(self, db: Session, payment_id: int) -> Optional[Payment]:
        return db.query(Payment).filter(Payment.id == payment_id).first()

    def get_by_invoice(self, db: Session, invoice_id: int) -> List[Payment]:
        return db.query(Payment).filter(Payment.invoice_id == invoice_id).all()

    def create(self, db: Session, invoice_id: int, amount: Decimal, payment_method: Optional[str] = None, payment_reference: Optional[str] = None, notes: Optional[str] = None, created_by: Optional[int] = None) -> Payment:
        db_obj = Payment(
            invoice_id=invoice_id,
            amount=amount,
            payment_method=payment_method,
            payment_reference=payment_reference,
            notes=notes,
            created_by=created_by,
        )
        db.add(db_obj)
        db.flush()
        invoice_repo.recalculate_payment_status(db, invoice_id)
        db.commit()
        db.refresh(db_obj)
        return db_obj


payment_repo = PaymentRepository()
