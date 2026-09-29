from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from typing import List

from app.db.session import get_db
from app.api.deps import get_current_user
from app.schemas.role import RoleCreate, RoleRead, RoleUpdate
from app.repositories.role_repository import role_repo
from app.utils.pagination import (
    DEFAULT_CATALOG_LIMIT,
    MAX_CATALOG_LIMIT,
    resolve_page,
    set_total_header,
)

router = APIRouter()


@router.get('/', response_model=List[RoleRead])
def list_roles(
    response: Response,
    skip: int = 0,
    limit: int = DEFAULT_CATALOG_LIMIT,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    skip, limit = resolve_page(skip, limit, max_limit=MAX_CATALOG_LIMIT)
    set_total_header(response, role_repo.count_all(db))
    return role_repo.get_all(db, skip=skip, limit=limit)


@router.get('/{role_id}', response_model=RoleRead)
def get_role(role_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    role = role_repo.get(db, role_id)
    if not role:
        raise HTTPException(status_code=404, detail='Role not found')
    return role


@router.post('/', response_model=RoleRead, status_code=201)
def create_role(data: RoleCreate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    from app.models.role import Role
    db_obj = Role(**data.model_dump())
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj


@router.put('/{role_id}', response_model=RoleRead)
def update_role(
    role_id: int,
    data: RoleUpdate,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    updated = role_repo.update(db, role_id, data.model_dump(exclude_none=True))
    if not updated:
        raise HTTPException(status_code=404, detail='Role not found')
    return updated


@router.delete('/{role_id}', status_code=204)
def delete_role(role_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    if not role_repo.delete(db, role_id):
        raise HTTPException(status_code=404, detail='Role not found')
