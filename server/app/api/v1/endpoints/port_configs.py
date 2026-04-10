from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.session import get_db
from app.api.deps import get_current_user
from app.repositories.port_config_repository import port_config_repo


class PortConfigRead(BaseModel):
    id: int
    key: str
    value: str
    description: Optional[str] = None

    model_config = {'from_attributes': True}


class PortConfigUpdate(BaseModel):
    value: str
    description: Optional[str] = None


class PortConfigCreate(BaseModel):
    key: str
    value: str
    description: Optional[str] = None


router = APIRouter()


@router.get('/', response_model=List[PortConfigRead])
def list_port_configs(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return port_config_repo.get_all(db)


@router.post('/', response_model=PortConfigRead, status_code=201)
def create_port_config(
    data: PortConfigCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if port_config_repo.get_by_key(db, data.key):
        raise HTTPException(status_code=409, detail='Config key already exists')
    return port_config_repo.create(
        db,
        key=data.key,
        value=data.value,
        description=data.description,
        updated_by=current_user.id,
    )


@router.get('/{key}', response_model=PortConfigRead)
def get_port_config(key: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    obj = port_config_repo.get_by_key(db, key)
    if not obj:
        raise HTTPException(status_code=404, detail='Config not found')
    return obj


@router.put('/{key}', response_model=PortConfigRead)
def upsert_port_config(key: str, data: PortConfigUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return port_config_repo.upsert(db, key=key, value=data.value, updated_by=current_user.id, description=data.description)


@router.delete('/{key}', status_code=204)
def delete_port_config(key: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    if not port_config_repo.delete_by_key(db, key):
        raise HTTPException(status_code=404, detail='Config not found')
