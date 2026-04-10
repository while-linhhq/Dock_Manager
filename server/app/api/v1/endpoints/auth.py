from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.user import UserCreate, UserRead
from app.services.auth_service import auth_service

router = APIRouter()


@router.post('/login')
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    return auth_service.login(db, form_data.username, form_data.password)


@router.post('/register', response_model=UserRead, status_code=201)
def register(data: UserCreate, db: Session = Depends(get_db)):
    return auth_service.register(
        db,
        username=data.username,
        password=data.password,
        email=data.email,
        full_name=data.full_name,
        phone=data.phone,
        role_id=data.role_id,
    )
