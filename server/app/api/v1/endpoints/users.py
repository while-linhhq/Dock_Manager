from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.db.session import get_db
from app.api.deps import get_current_user
from app.schemas.user import UserRead, UserUpdate
from app.repositories.user_repository import user_repo

router = APIRouter()


@router.get('/', response_model=List[UserRead])
def list_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return user_repo.get_all(db, skip=skip, limit=limit)


@router.get('/me', response_model=UserRead)
def get_me(current_user=Depends(get_current_user)):
    return current_user


@router.get('/{user_id}', response_model=UserRead)
def get_user(user_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    user = user_repo.get(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail='User not found')
    return user


@router.put('/{user_id}', response_model=UserRead)
def update_user(user_id: int, data: UserUpdate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    updated = user_repo.update(db, user_id, **data.model_dump(exclude_none=True))
    if not updated:
        raise HTTPException(status_code=404, detail='User not found')
    return updated


@router.delete('/{user_id}', status_code=204)
def deactivate_user(user_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    if not user_repo.delete(db, user_id):
        raise HTTPException(status_code=404, detail='User not found')
