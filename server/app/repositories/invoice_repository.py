import secrets
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.models.invoice import Invoice
from app.models.invoice_item import InvoiceItem
from app.models.payment import Payment
from typing import List, Optional


class InvoiceRepository:
    def get(self, db: Session, invoice_id: int, include_deleted: bool = False) -> Optional[Invoice]:
        q = (
            db.query(Invoice)
            .options(
                joinedload(Invoice.creator),
                joinedload(Invoice.items).joinedload(InvoiceItem.fee_config),
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
            cand = f"INV-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(3).upper()}"
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

    def get_by_detection_id(self, db: Session, detection_id: int) -> Optional[Invoice]:
        return (
            db.query(Invoice)
            .filter(Invoice.detection_id == detection_id)
            .filter(Invoice.deleted_at.is_(None))
            .first()
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
    ) -> List[Invoice]:
        q = db.query(Invoice).options(
            joinedload(Invoice.creator),
            joinedload(Invoice.items).joinedload(InvoiceItem.fee_config),
        )
        if deleted_only:
            q = q.filter(Invoice.deleted_at.isnot(None))
            q = q.order_by(Invoice.deleted_at.desc())
        else:
            q = q.filter(Invoice.deleted_at.is_(None))
            if awaiting_payment is True:
                q = q.filter(Invoice.payment_status != 'PAID')
            elif payment_status:
                q = q.filter(Invoice.payment_status == payment_status)
            q = q.order_by(Invoice.created_at.desc())
        if creation_source:
            q = q.filter(Invoice.creation_source == creation_source)
        elif exclude_creation_source:
            q = q.filter(
                or_(
                    Invoice.creation_source.is_(None),
                    Invoice.creation_source != exclude_creation_source,
                )
            )
        return q.offset(skip).limit(limit).all()

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
        """Soft-delete: sets deleted_at. Payments and rows are kept for audit."""
        db_obj = self.get(db, invoice_id, include_deleted=False)
        if not db_obj:
            return False
        db_obj.deleted_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(db_obj)
        return True


invoice_repo = InvoiceRepository()
