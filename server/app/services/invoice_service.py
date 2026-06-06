from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.repositories.invoice_repository import invoice_repo
from app.repositories.invoice_item_repository import invoice_item_repo
from app.repositories.port_config_repository import port_config_repo
from app.schemas.invoice import InvoiceCreate
from app.models.invoice import Invoice
from app.services.berth_limit_service import compute_invoice_over_berth_limit
from app.services.fee_penalty_service import compute_invoice_outside_operating_hours


def compute_invoice_gross(
    subtotal: Optional[Decimal],
    tax_amount: Optional[Decimal],
    *,
    total_amount: Optional[Decimal] = None,
    discount_amount: Optional[Decimal] = None,
) -> Decimal:
    """Tổng trước giảm giá: subtotal + tax, hoặc total hiện tại + discount đã áp dụng."""
    sub = (subtotal or Decimal('0')).quantize(Decimal('0.01'))
    tax = (tax_amount or Decimal('0')).quantize(Decimal('0.01'))
    from_items = (sub + tax).quantize(Decimal('0.01'))
    if from_items > 0:
        return from_items
    total = (total_amount or Decimal('0')).quantize(Decimal('0.01'))
    disc = (discount_amount or Decimal('0')).quantize(Decimal('0.01'))
    return max((total + disc).quantize(Decimal('0.01')), Decimal('0'))


def compute_invoice_total(
    subtotal: Optional[Decimal],
    tax_amount: Optional[Decimal],
    discount_amount: Optional[Decimal],
    *,
    total_amount: Optional[Decimal] = None,
    current_discount_amount: Optional[Decimal] = None,
) -> Decimal:
    gross = compute_invoice_gross(
        subtotal,
        tax_amount,
        total_amount=total_amount,
        discount_amount=current_discount_amount,
    )
    disc = (discount_amount or Decimal('0')).quantize(Decimal('0.01'))
    if disc < 0:
        disc = Decimal('0')
    if disc > gross:
        disc = gross
    total = (gross - disc).quantize(Decimal('0.01'))
    return max(total, Decimal('0'))


class InvoiceService:
    def create_with_items(self, db: Session, data: InvoiceCreate) -> Invoice:
        # Fetch tax rate from port_configs (default 10%)
        tax_cfg = port_config_repo.get_by_key(db, 'invoice_tax_rate')
        tax_rate = Decimal(tax_cfg.value) if tax_cfg else Decimal('0.1')

        items_data = [item.model_dump() for item in data.items]

        # Recalculate subtotal from items if not provided
        subtotal = data.subtotal
        if subtotal is None and items_data:
            subtotal = sum(Decimal(str(i.get('amount', 0))) for i in items_data)

        tax_amount = data.tax_amount
        if tax_amount is None and subtotal is not None:
            tax_amount = (subtotal * tax_rate).quantize(Decimal('0.01'))

        discount_amount = (data.discount_amount or Decimal('0')).quantize(Decimal('0.01'))
        if discount_amount < 0:
            discount_amount = Decimal('0')

        total_amount = data.total_amount
        if total_amount is None:
            total_amount = compute_invoice_total(subtotal, tax_amount, discount_amount)

        invoice_data = data.model_dump(exclude={'items'})
        invoice_data.update({
            'subtotal': subtotal,
            'tax_amount': tax_amount,
            'discount_amount': discount_amount,
            'total_amount': total_amount,
        })

        invoice = invoice_repo.create(db, invoice_data)

        if items_data:
            for item in items_data:
                item['invoice_id'] = invoice.id
            invoice_item_repo.create_bulk(db, items_data)

        db.flush()
        refreshed = invoice_repo.get(db, invoice.id)
        if refreshed:
            refreshed.is_over_berth_limit = compute_invoice_over_berth_limit(db, refreshed)
            refreshed.is_outside_operating_hours = compute_invoice_outside_operating_hours(
                db,
                refreshed,
            )

        db.commit()
        db.refresh(invoice)
        return invoice_repo.get(db, invoice.id) or invoice


invoice_service = InvoiceService()
