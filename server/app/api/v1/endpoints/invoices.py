from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.session import get_db
from app.api.deps import get_current_user
from app.schemas.invoice import InvoiceCreate, InvoiceRead, InvoiceUpdate
from app.schemas.payment import PaymentCreate, PaymentRead
from app.repositories.invoice_repository import invoice_repo
from app.repositories.order_repository import order_repo
from app.repositories.payment_repository import payment_repo
from app.services.detection_invoice_service import backfill_missing_ai_invoices
from app.services.invoice_service import invoice_service

router = APIRouter()


@router.get('/', response_model=List[InvoiceRead])
def list_invoices(
    skip: int = 0,
    limit: int = 100,
    payment_status: Optional[str] = None,
    awaiting_payment: Optional[bool] = Query(None, description='Mọi trạng thái trừ PAID (chờ / một phần / quá hạn / hủy…)'),
    deleted_only: bool = Query(False, description='Chỉ hóa đơn đã xóa mềm'),
    creation_source: Optional[str] = Query(
        None,
        description='Lọc đúng nguồn tạo (VD: AI = hóa đơn tự động từ nhận dạng)',
    ),
    exclude_creation_source: Optional[str] = Query(
        None,
        description='Loại trừ nguồn (VD: AI để tab hóa đơn thủ công/đơn hàng)',
    ),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    return invoice_repo.get_all(
        db,
        skip=skip,
        limit=limit,
        payment_status=payment_status,
        awaiting_payment=awaiting_payment,
        deleted_only=deleted_only,
        creation_source=creation_source,
        exclude_creation_source=exclude_creation_source,
    )


@router.get('/{invoice_id}', response_model=InvoiceRead)
def get_invoice(invoice_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    obj = invoice_repo.get(db, invoice_id)
    if not obj:
        raise HTTPException(status_code=404, detail='Invoice not found')
    return obj


@router.post('/backfill-ai')
def backfill_ai_invoices(
    limit: int = Query(200, ge=1, le=5000, description='Số detection cũ tối đa cần backfill'),
    _=Depends(get_current_user),
):
    """
    Backfill hóa đơn AI cho detection cũ chưa có invoice.
    Dùng cho kiểm tra tính năng sau khi cập nhật logic AI invoice.
    """
    result = backfill_missing_ai_invoices(limit=limit)
    return {
        'success': True,
        **result,
    }


@router.post('/', response_model=InvoiceRead, status_code=201)
def create_invoice(data: InvoiceCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    inv_no = (data.invoice_number or '').strip() or invoice_repo.generate_unique_invoice_number(db)
    vessel_id = data.vessel_id
    if data.order_id is not None and vessel_id is None:
        ord_row = order_repo.get(db, data.order_id)
        if ord_row and ord_row.vessel_id is not None:
            vessel_id = ord_row.vessel_id
    # ORDER_AUTO / AI chỉ gán từ dịch vụ nội bộ, không tin body client
    payload = data.model_copy(
        update={
            'invoice_number': inv_no,
            'vessel_id': vessel_id,
            'created_by': data.created_by or current_user.id,
            'creation_source': 'USER',
        },
    )
    return invoice_service.create_with_items(db, payload)


@router.put('/{invoice_id}', response_model=InvoiceRead)
def update_invoice(
    invoice_id: int,
    data: InvoiceUpdate,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    payload = data.model_dump(exclude_none=True)
    if not payload:
        obj = invoice_repo.get(db, invoice_id)
        if not obj:
            raise HTTPException(status_code=404, detail='Invoice not found')
        return obj
    updated = invoice_repo.update(db, invoice_id, payload)
    if not updated:
        raise HTTPException(status_code=404, detail='Invoice not found')
    return updated


@router.delete('/{invoice_id}', status_code=204)
def delete_invoice(invoice_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Soft-delete (deleted_at). Listed under deleted_only=true."""
    if not invoice_repo.delete(db, invoice_id):
        raise HTTPException(status_code=404, detail='Invoice not found')


@router.post('/{invoice_id}/payments', response_model=PaymentRead, status_code=201)
def add_payment(invoice_id: int, data: PaymentCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    invoice = invoice_repo.get(db, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail='Invoice not found')
    data = data.model_copy(update={'invoice_id': invoice_id, 'created_by': current_user.id})
    payment = payment_repo.create(db, invoice_id=invoice_id, amount=data.amount, payment_method=data.payment_method, payment_reference=data.payment_reference, notes=data.notes, created_by=current_user.id)
    return payment


@router.get('/{invoice_id}/payments', response_model=List[PaymentRead])
def list_payments(invoice_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return payment_repo.get_by_invoice(db, invoice_id)
