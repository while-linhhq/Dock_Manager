from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.session import get_db
from app.api.deps import get_current_user, require_discount_approver
from app.schemas.invoice import DiscountReject, InvoiceCreate, InvoiceRead, InvoiceUpdate
from app.schemas.payment import (
    BulkPaymentCreate,
    BulkPaymentRead,
    BulkSepaySessionCreate,
    BulkSepaySessionRead,
    PaymentCreate,
    PaymentRead,
)
from app.schemas.sepay import InvoicePaymentStatusRead
from app.repositories.invoice_repository import invoice_repo
from app.repositories.order_repository import order_repo
from app.repositories.payment_repository import payment_repo
from app.services.detection_invoice_service import backfill_missing_ai_invoices
from app.services.discount_approval_service import approve_discount, reject_discount, request_discount
from app.services.invoice_service import invoice_service
from app.services.berth_limit_service import compute_invoice_over_berth_limit
from app.services.fee_penalty_service import compute_invoice_outside_operating_hours
from app.services.invoice_snapshot_service import is_invoice_financially_locked
from app.services.bulk_sepay_service import create_bulk_sepay_session, sync_bulk_sepay_session
from app.services.invoice_payment_service import bulk_record_payments
from app.services.sepay_sync_service import sync_sepay_payments

router = APIRouter()


def _invoice_to_read(db: Session, inv) -> InvoiceRead:
    payload = InvoiceRead.model_validate(inv)
    if is_invoice_financially_locked(inv):
        return payload
    over = compute_invoice_over_berth_limit(db, inv)
    outside = compute_invoice_outside_operating_hours(db, inv)
    return payload.model_copy(
        update={
            'is_over_berth_limit': over,
            'is_outside_operating_hours': outside,
        },
    )


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
    rows = invoice_repo.get_all(
        db,
        skip=skip,
        limit=limit,
        payment_status=payment_status,
        awaiting_payment=awaiting_payment,
        deleted_only=deleted_only,
        creation_source=creation_source,
        exclude_creation_source=exclude_creation_source,
    )
    return [_invoice_to_read(db, inv) for inv in rows]


@router.get('/discount-requests', response_model=List[InvoiceRead])
def list_discount_requests(
    status: str = Query('pending', description='pending | approved | rejected'),
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    _=Depends(require_discount_approver),
):
    normalized = (status or 'pending').strip().lower()
    if normalized not in {'pending', 'approved', 'rejected'}:
        raise HTTPException(status_code=422, detail='status không hợp lệ')
    rows = invoice_repo.get_by_discount_status(db, normalized, skip=skip, limit=limit)
    return [_invoice_to_read(db, inv) for inv in rows]


@router.post('/bulk-payments', response_model=BulkPaymentRead, status_code=201)
def bulk_payments(
    data: BulkPaymentCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    method = (data.payment_method or 'cash').strip().lower()
    if not method:
        raise HTTPException(status_code=422, detail='payment_method is required')
    payments, total = bulk_record_payments(
        db,
        data.invoice_ids,
        payment_method=method,
        created_by=current_user.id,
        notes=data.notes,
    )
    if not payments:
        raise HTTPException(status_code=400, detail='No payable invoices in the request')
    return BulkPaymentRead(
        invoice_count=len(payments),
        total_amount=total,
        payments=[PaymentRead.model_validate(p) for p in payments],
    )


@router.post('/bulk-sepay-session', response_model=BulkSepaySessionRead, status_code=status.HTTP_201_CREATED)
def create_bulk_sepay_payment_session(
    data: BulkSepaySessionCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        session = create_bulk_sepay_session(
            db,
            data.invoice_ids,
            created_by=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    ids = [int(x) for x in (session.invoice_ids or [])]
    return BulkSepaySessionRead(
        reference_code=session.reference_code,
        invoice_count=len(ids),
        total_amount=session.expected_total,
        status=session.status,
        invoice_ids=ids,
    )


@router.get('/bulk-sepay-session/{reference_code}', response_model=BulkSepaySessionRead)
def get_bulk_sepay_payment_session(
    reference_code: str,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    try:
        session = sync_bulk_sepay_session(db, reference_code.strip().upper())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    ids = [int(x) for x in (session.invoice_ids or [])]
    return BulkSepaySessionRead(
        reference_code=session.reference_code,
        invoice_count=len(ids),
        total_amount=session.expected_total,
        status=session.status,
        invoice_ids=ids,
    )


@router.get('/{invoice_id:int}/payment-status', response_model=InvoicePaymentStatusRead)
def get_invoice_payment_status(
    invoice_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    obj = invoice_repo.get(db, invoice_id)
    if not obj:
        raise HTTPException(status_code=404, detail='Invoice not found')

    if (obj.payment_status or '').upper() != 'PAID' and obj.invoice_number:
        sync_sepay_payments(db, invoice_number=obj.invoice_number)
        db.refresh(obj)

    return InvoicePaymentStatusRead(
        payment_status=obj.payment_status or 'UNPAID',
        paid_at=obj.paid_at,
    )


@router.get('/{invoice_id:int}', response_model=InvoiceRead)
def get_invoice(invoice_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    obj = invoice_repo.get(db, invoice_id)
    if not obj:
        raise HTTPException(status_code=404, detail='Invoice not found')
    return _invoice_to_read(db, obj)


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
    created = invoice_service.create_with_items(db, payload)
    return _invoice_to_read(db, created)


@router.put('/{invoice_id:int}', response_model=InvoiceRead)
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
        return _invoice_to_read(db, obj)

    obj = invoice_repo.get(db, invoice_id)
    if not obj:
        raise HTTPException(status_code=404, detail='Invoice not found')
    if is_invoice_financially_locked(obj):
        allowed = {'notes'}
        if set(payload.keys()) - allowed:
            raise HTTPException(
                status_code=400,
                detail='Hóa đơn đã thanh toán — không thể sửa thông tin tài chính hoặc mã tàu.',
            )

    if 'discount_requested_amount' in payload:
        try:
            requested = Decimal(str(payload['discount_requested_amount'])).quantize(Decimal('0.01'))
        except Exception as exc:
            raise HTTPException(status_code=422, detail='discount_requested_amount không hợp lệ') from exc
        try:
            updated_inv = request_discount(db, obj, requested)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return _invoice_to_read(db, updated_inv)

    payload.pop('discount_amount', None)
    updated = invoice_repo.update(db, invoice_id, payload)
    if not updated:
        raise HTTPException(status_code=404, detail='Invoice not found')
    return _invoice_to_read(db, updated)


@router.post('/{invoice_id:int}/discount/approve', response_model=InvoiceRead)
def approve_invoice_discount(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_discount_approver),
):
    obj = invoice_repo.get(db, invoice_id)
    if not obj:
        raise HTTPException(status_code=404, detail='Invoice not found')
    try:
        updated = approve_discount(db, obj, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _invoice_to_read(db, updated)


@router.post('/{invoice_id:int}/discount/reject', response_model=InvoiceRead)
def reject_invoice_discount(
    invoice_id: int,
    data: DiscountReject,
    db: Session = Depends(get_db),
    current_user=Depends(require_discount_approver),
):
    obj = invoice_repo.get(db, invoice_id)
    if not obj:
        raise HTTPException(status_code=404, detail='Invoice not found')
    try:
        updated = reject_discount(db, obj, current_user.id, data.reason)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _invoice_to_read(db, updated)


@router.delete('/{invoice_id:int}', status_code=204)
def delete_invoice(invoice_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Soft-delete (deleted_at). Listed under deleted_only=true."""
    if not invoice_repo.delete(db, invoice_id):
        raise HTTPException(status_code=404, detail='Invoice not found')


@router.post('/{invoice_id:int}/payments', response_model=PaymentRead, status_code=201)
def add_payment(invoice_id: int, data: PaymentCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    invoice = invoice_repo.get(db, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail='Invoice not found')
    data = data.model_copy(update={'invoice_id': invoice_id, 'created_by': current_user.id})
    payment = payment_repo.create(db, invoice_id=invoice_id, amount=data.amount, payment_method=data.payment_method, payment_reference=data.payment_reference, notes=data.notes, created_by=current_user.id)
    return payment


@router.get('/{invoice_id:int}/payments', response_model=List[PaymentRead])
def list_payments(invoice_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return payment_repo.get_by_invoice(db, invoice_id)
