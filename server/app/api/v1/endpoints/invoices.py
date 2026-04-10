from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.session import get_db
from app.api.deps import get_current_user
from app.schemas.invoice import InvoiceCreate, InvoiceRead, InvoiceUpdate
from app.schemas.payment import PaymentCreate, PaymentRead
from app.repositories.invoice_repository import invoice_repo
from app.repositories.payment_repository import payment_repo
from app.services.invoice_service import invoice_service

router = APIRouter()


@router.get('/', response_model=List[InvoiceRead])
def list_invoices(skip: int = 0, limit: int = 100, payment_status: Optional[str] = None, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return invoice_repo.get_all(db, skip=skip, limit=limit, payment_status=payment_status)


@router.get('/{invoice_id}', response_model=InvoiceRead)
def get_invoice(invoice_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    obj = invoice_repo.get(db, invoice_id)
    if not obj:
        raise HTTPException(status_code=404, detail='Invoice not found')
    return obj


@router.post('/', response_model=InvoiceRead, status_code=201)
def create_invoice(data: InvoiceCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if not data.created_by:
        data = data.model_copy(update={'created_by': current_user.id})
    return invoice_service.create_with_items(db, data)


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
