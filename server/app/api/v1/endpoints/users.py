from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List

from app.db.session import get_db
from app.api.deps import get_current_user
from app.schemas.user import UserCreate, UserRead, UserSelfUpdate, UserUpdate
from app.repositories.user_repository import user_repo
from app.utils.security import hash_password

router = APIRouter()


def _is_admin(user) -> bool:
    if user is None:
        return False
    username = (getattr(user, 'username', '') or '').strip().lower()
    if username == 'admin':
        return True
    if user.role is None:
        return False
    role_name = (user.role.role_name or '').strip().lower()
    if role_name == 'admin':
        return True
    perms = user.role.permissions or {}
    return bool(perms.get('all') is True)


@router.get('/', response_model=List[UserRead])
def list_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return user_repo.get_all(db, skip=skip, limit=limit)


@router.post('/', response_model=UserRead, status_code=201)
def create_user(data: UserCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail='Only admin can create users')
    if user_repo.get_by_username(db, data.username):
        raise HTTPException(status_code=400, detail='Username already exists')
    if data.email and user_repo.get_by_email(db, data.email):
        raise HTTPException(status_code=400, detail='Email already exists')
    return user_repo.create(
        db,
        username=data.username,
        hashed_password=hash_password(data.password),
        email=data.email,
        full_name=data.full_name,
        phone=data.phone,
        role_id=data.role_id,
        is_active=data.is_active,
    )


@router.get('/me', response_model=UserRead)
def get_me(current_user=Depends(get_current_user)):
    return current_user


@router.put('/me', response_model=UserRead)
def update_me(data: UserSelfUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    payload = data.model_dump(exclude_none=True)
    if not payload:
        return current_user
    if 'email' in payload and payload['email']:
        existing = user_repo.get_by_email(db, payload['email'])
        if existing and existing.id != current_user.id:
            raise HTTPException(status_code=400, detail='Email already exists')
    if 'password' in payload:
        pwd = payload.pop('password')
        if pwd:
            payload['hashed_password'] = hash_password(pwd)
    updated = user_repo.update(db, int(current_user.id), **payload)
    if not updated:
        raise HTTPException(status_code=404, detail='User not found')
    return updated


@router.get('/{user_id}', response_model=UserRead)
def get_user(user_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    user = user_repo.get(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail='User not found')
    return user


@router.put('/{user_id}', response_model=UserRead)
def update_user(user_id: int, data: UserUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail='Only admin can update other users')
    updated = user_repo.update(db, user_id, **data.model_dump(exclude_none=True))
    if not updated:
        raise HTTPException(status_code=404, detail='User not found')
    return updated


@router.delete('/{user_id}', status_code=204)
def delete_user(user_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail='Only admin can delete users')
    if int(current_user.id) == user_id:
        raise HTTPException(status_code=400, detail='Cannot delete your own account')
    try:
        deleted = user_repo.delete(db, user_id)
    except IntegrityError:
        raise HTTPException(
            status_code=409,
            detail='Cannot delete user: still referenced without ON DELETE rule',
        ) from None
    if not deleted:
        raise HTTPException(status_code=404, detail='User not found')
