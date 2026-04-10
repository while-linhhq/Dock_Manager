from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.utils.security import hash_password, verify_password, create_access_token
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
        token = create_access_token(subject=user.id)
        return {'access_token': token, 'token_type': 'bearer'}


auth_service = AuthService()
