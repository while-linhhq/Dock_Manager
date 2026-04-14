from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.schemas.user import UserCreate, UserRead
from app.services.auth_service import auth_service

router = APIRouter()


@router.post('/login')
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    return auth_service.login(db, form_data.username, form_data.password)

@router.post('/refresh')
def refresh(_=Depends(get_current_user)):
    """
    Sliding-session refresh: client calls this before token expires to get a new access token.
    Requires a still-valid access token.
    """
    return auth_service.refresh_access_token(current_user=_)


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
