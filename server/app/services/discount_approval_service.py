from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.invoice import Invoice
from app.services.invoice_service import compute_invoice_gross, compute_invoice_total


def _gross_for_invoice(inv: Invoice) -> Decimal:
    return compute_invoice_gross(
        inv.subtotal,
        inv.tax_amount,
        total_amount=inv.total_amount,
        discount_amount=inv.discount_amount if (inv.discount_status or 'none') == 'approved' else Decimal('0'),
    )


def request_discount(db: Session, inv: Invoice, requested_amount: Decimal) -> Invoice:
    gross = _gross_for_invoice(inv)
    amount = requested_amount.quantize(Decimal('0.01'))
    if amount < 0:
        raise ValueError('discount_requested_amount phải >= 0')
    if amount > gross:
        raise ValueError('discount_requested_amount không được vượt tổng trước giảm')

    inv.discount_requested_amount = amount
    inv.discount_reviewed_at = None
    inv.discount_reviewed_by = None
    inv.discount_reject_reason = None

    if amount <= 0:
        inv.discount_status = 'none'
        inv.discount_amount = Decimal('0')
        inv.total_amount = gross
    else:
        inv.discount_status = 'pending'
        inv.discount_amount = Decimal('0')
        inv.total_amount = gross

    db.commit()
    db.refresh(inv)
    return inv


def approve_discount(db: Session, inv: Invoice, reviewer_id: int) -> Invoice:
    status = (inv.discount_status or 'none').lower()
    if status != 'pending':
        raise ValueError('Hóa đơn không có yêu cầu giảm giá đang chờ duyệt')

    amount = (inv.discount_requested_amount or Decimal('0')).quantize(Decimal('0.01'))
    gross = _gross_for_invoice(inv)
    if amount <= 0 or amount > gross:
        raise ValueError('Số tiền giảm giá yêu cầu không hợp lệ')

    inv.discount_amount = amount
    inv.discount_status = 'approved'
    inv.total_amount = compute_invoice_total(
        inv.subtotal,
        inv.tax_amount,
        amount,
        total_amount=inv.total_amount,
        current_discount_amount=Decimal('0'),
    )
    inv.discount_reviewed_at = datetime.now(timezone.utc)
    inv.discount_reviewed_by = reviewer_id
    inv.discount_reject_reason = None

    db.commit()
    db.refresh(inv)
    return inv


def reject_discount(
    db: Session,
    inv: Invoice,
    reviewer_id: int,
    reason: Optional[str] = None,
) -> Invoice:
    status = (inv.discount_status or 'none').lower()
    if status != 'pending':
        raise ValueError('Hóa đơn không có yêu cầu giảm giá đang chờ duyệt')

    gross = _gross_for_invoice(inv)
    inv.discount_status = 'rejected'
    inv.discount_amount = Decimal('0')
    inv.total_amount = gross
    inv.discount_reviewed_at = datetime.now(timezone.utc)
    inv.discount_reviewed_by = reviewer_id
    inv.discount_reject_reason = (reason or '').strip() or None

    db.commit()
    db.refresh(inv)
    return inv
