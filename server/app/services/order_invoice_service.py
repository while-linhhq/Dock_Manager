"""
Tạo hóa đơn kèm đơn hàng: line items từ fee_configs theo loại tàu;
total_amount = 0 để quản lý tự nhập (giữ nguyên nếu đơn có total_amount > 0 làm gợi ý).
"""

from decimal import Decimal

from sqlalchemy.orm import Session, joinedload

from app.models.order import Order
from app.models.vessel import Vessel
from app.repositories.fee_config_repository import fee_config_repo
from app.repositories.invoice_repository import invoice_repo
from app.schemas.invoice import InvoiceCreate, InvoiceItemCreate
from app.services.invoice_service import invoice_service


def ensure_invoice_for_order(db: Session, order: Order, acting_user_id: int) -> None:
    """
    Gọi sau khi order đã flush trong cùng session (chưa commit).
    invoice_service.create_with_items sẽ commit toàn bộ transaction.
    """
    if not order.vessel_id:
        db.commit()
        return

    vessel = (
        db.query(Vessel)
        .options(joinedload(Vessel.vessel_type))
        .filter(Vessel.id == order.vessel_id)
        .first()
    )
    if not vessel:
        db.commit()
        return

    items: list[InvoiceItemCreate] = []
    if vessel.vessel_type_id:
        for f in fee_config_repo.get_by_vessel_type(db, vessel.vessel_type_id):
            items.append(
                InvoiceItemCreate(
                    fee_config_id=f.id,
                    description=f.fee_name,
                    quantity=Decimal('1'),
                    unit_price=f.base_fee,
                    amount=f.base_fee,
                )
            )

    type_name = vessel.vessel_type.type_name if vessel.vessel_type else '—'
    notes_lines = [
        f'Hóa đơn tự động từ đơn {order.order_number}.',
        f'Tàu / loại: {vessel.ship_id} — loại tàu: {type_name}.',
        'Dòng phí: tham chiếu theo cấu hình phí loại tàu. Nhập tổng tiền khi duyệt.',
    ]
    if order.description:
        notes_lines.append(f'Hàng hóa (đơn): {order.description}')

    suggested = order.total_amount
    if suggested is not None:
        try:
            sug_dec = Decimal(str(suggested))
            total_amt = sug_dec if sug_dec > 0 else Decimal('0')
        except Exception:
            total_amt = Decimal('0')
    else:
        total_amt = Decimal('0')

    inv_no = invoice_repo.generate_unique_invoice_number(db)
    data = InvoiceCreate(
        invoice_number=inv_no,
        order_id=order.id,
        vessel_id=order.vessel_id,
        total_amount=total_amt,
        notes='\n'.join(notes_lines),
        creation_source='ORDER_AUTO',
        created_by=acting_user_id,
        items=items,
    )
    invoice_service.create_with_items(db, data)
