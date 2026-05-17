"""Paid-invoice guard — chỉ khóa khi payment_status = PAID."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.invoice import Invoice
from app.services.berth_limit_service import compute_invoice_over_berth_limit


def is_invoice_financially_locked(invoice: Invoice) -> bool:
    return (invoice.payment_status or '').upper() == 'PAID'


def seal_invoice_on_paid(db: Session, invoice: Invoice) -> None:
    """Ghi cờ quá giới hạn neo tại thời điểm thanh toán (không tính lại sau)."""
    invoice.is_over_berth_limit = compute_invoice_over_berth_limit(db, invoice)
    db.flush()
