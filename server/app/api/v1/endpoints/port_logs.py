from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date
from typing import List, Optional

from app.db.session import get_db
from app.api.deps import get_current_user
from app.schemas.port_log import PortLogRead
from app.repositories.port_log_repository import port_log_repo

router = APIRouter()


@router.get('/', response_model=List[PortLogRead])
def list_port_logs(
    skip: int = 0,
    limit: int = 100,
    ship_id: Optional[str] = None,
    log_date: Optional[date] = None,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    return port_log_repo.get_all_logs(db, skip=skip, limit=limit, ship_id=ship_id, log_date=log_date)


@router.get('/{log_id}', response_model=PortLogRead)
def get_port_log(log_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    obj = port_log_repo.get(db, log_id)
    if not obj:
        raise HTTPException(status_code=404, detail='Port log not found')
    return obj


@router.delete('/{log_id}', status_code=204)
def delete_port_log(log_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    if not port_log_repo.delete(db, log_id):
        raise HTTPException(status_code=404, detail='Port log not found')
