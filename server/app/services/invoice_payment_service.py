"""Thanh toán hóa đơn — số tiền còn lại và ghi nhận hàng loạt."""
from __future__ import annotations

from decimal import Decimal
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.invoice import Invoice
from app.models.payment import Payment
from app.repositories.invoice_repository import invoice_repo
from app.repositories.payment_repository import payment_repo
from app.services.invoice_snapshot_service import is_invoice_financially_locked


def invoice_amount_due(db: Session, invoice: Invoice) -> Decimal:
    total = (invoice.total_amount or Decimal('0')).quantize(Decimal('0.01'))
    paid_raw = (
        db.query(func.coalesce(func.sum(Payment.amount), 0))
        .filter(Payment.invoice_id == invoice.id)
        .scalar()
    )
    paid = Decimal(str(paid_raw or 0)).quantize(Decimal('0.01'))
    return max(total - paid, Decimal('0'))


def bulk_record_payments(
    db: Session,
    invoice_ids: List[int],
    *,
    payment_method: str,
    created_by: int,
    notes: Optional[str] = None,
) -> tuple[List[Payment], Decimal]:
    """Ghi nhận thanh toán cho nhiều HĐ trong một transaction."""
    payments: List[Payment] = []
    total = Decimal('0')

    for invoice_id in invoice_ids:
        inv = invoice_repo.get(db, invoice_id)
        if not inv:
            continue
        if is_invoice_financially_locked(inv):
            continue
        due = invoice_amount_due(db, inv)
        if due <= 0:
            continue
        row = payment_repo._create_payment_row(
            db,
            invoice_id,
            due,
            payment_method=payment_method,
            notes=notes,
            created_by=created_by,
        )
        payments.append(row)
        total += due

    if payments:
        db.commit()
        for row in payments:
            db.refresh(row)
    return payments, total.quantize(Decimal('0.01'))
