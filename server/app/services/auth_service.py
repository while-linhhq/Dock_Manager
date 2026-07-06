from fastapi import HTTPException, status
from jose import JWTError
from sqlalchemy.orm import Session

from app.utils.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.repositories.user_repository import user_repo
from app.models.user import User


class AuthService:
    def register(self, db: Session, username: str, password: str, **kwargs) -> User:
        if user_repo.get_by_username(db, username):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Username already exists')
        if kwargs.get('email') and user_repo.get_by_email(db, kwargs['email']):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Email already registered')
        return user_repo.create(db, username=username, hashed_password=hash_password(password), **kwargs)

    def login(self, db: Session, username: str, password: str) -> dict:
        user = user_repo.get_by_username(db, username)
        if not user or not verify_password(password, user.hashed_password or ''):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='Incorrect username or password',
            )
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Inactive user')
        return {
            'access_token': create_access_token(subject=user.id),
            'refresh_token': create_refresh_token(subject=user.id),
            'token_type': 'bearer',
        }

    def refresh_access_token(self, db: Session, refresh_token: str) -> dict:
        """Validate a refresh token (no access token required) and mint a new pair."""
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Could not validate refresh token',
            headers={'WWW-Authenticate': 'Bearer'},
        )
        try:
            payload = decode_token(refresh_token)
        except JWTError:
            raise credentials_exception
        if payload.get('type') != 'refresh':
            raise credentials_exception
        user_id = payload.get('sub')
        if user_id is None:
            raise credentials_exception
        try:
            user = user_repo.get(db, int(user_id))
        except (TypeError, ValueError):
            raise credentials_exception
        if user is None or not user.is_active:
            raise credentials_exception
        return {
            'access_token': create_access_token(subject=user.id),
            'refresh_token': create_refresh_token(subject=user.id),
            'token_type': 'bearer',
        }


auth_service = AuthService()
