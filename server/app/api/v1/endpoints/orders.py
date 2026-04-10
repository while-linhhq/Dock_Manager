from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.session import get_db
from app.api.deps import get_current_user
from app.schemas.order import OrderCreate, OrderUpdate, OrderStatusUpdate, OrderRead
from app.repositories.order_repository import order_repo

router = APIRouter()


@router.get('/', response_model=List[OrderRead])
def list_orders(skip: int = 0, limit: int = 100, status: Optional[str] = None, db: Session = Depends(get_db)):
    return order_repo.get_all(db, skip=skip, limit=limit, status=status)


@router.get('/{order_id}', response_model=OrderRead)
def get_order(order_id: int, db: Session = Depends(get_db)):
    obj = order_repo.get(db, order_id)
    if not obj:
        raise HTTPException(status_code=404, detail='Order not found')
    return obj


@router.post('/', response_model=OrderRead, status_code=201)
def create_order(data: OrderCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if not data.created_by:
        data = data.model_copy(update={'created_by': current_user.id})
    return order_repo.create(db, data)


@router.put('/{order_id}', response_model=OrderRead)
def update_order(order_id: int, data: OrderUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    payload = data.model_dump(exclude_none=True)
    payload['updated_by'] = current_user.id
    updated = order_repo.update(db, order_id, payload)
    if not updated:
        raise HTTPException(status_code=404, detail='Order not found')
    return updated


@router.patch('/{order_id}/status', response_model=OrderRead)
def update_order_status(order_id: int, data: OrderStatusUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    updated = order_repo.update_status(db, order_id, data.status, updated_by=current_user.id)
    if not updated:
        raise HTTPException(status_code=404, detail='Order not found')
    return updated


@router.delete('/{order_id}', status_code=204)
def delete_order(order_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    if not order_repo.delete(db, order_id):
        raise HTTPException(status_code=404, detail='Order not found')
