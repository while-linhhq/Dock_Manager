from decimal import Decimal
from sqlalchemy.orm import Session

from app.repositories.invoice_repository import invoice_repo
from app.repositories.invoice_item_repository import invoice_item_repo
from app.repositories.port_config_repository import port_config_repo
from app.schemas.invoice import InvoiceCreate
from app.models.invoice import Invoice


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

        total_amount = data.total_amount
        if subtotal is not None and tax_amount is not None:
            total_amount = subtotal + tax_amount

        invoice_data = data.model_dump(exclude={'items'})
        invoice_data.update({'subtotal': subtotal, 'tax_amount': tax_amount, 'total_amount': total_amount})

        invoice = invoice_repo.create(db, invoice_data)

        if items_data:
            for item in items_data:
                item['invoice_id'] = invoice.id
            invoice_item_repo.create_bulk(db, items_data)

        db.commit()
        db.refresh(invoice)
        return invoice


invoice_service = InvoiceService()
