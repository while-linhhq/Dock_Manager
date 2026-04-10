from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl='/api/v1/auth/login')


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    """FastAPI dependency to get the current authenticated user."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail='Could not validate credentials',
        headers={'WWW-Authenticate': 'Bearer'},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get('sub')
        if user_id is None:
            raise credentials_exception
    except JWTError as e:
        print(f"JWT Decode Error: {str(e)}")
        raise credentials_exception

    from app.repositories.user_repository import user_repo
    try:
        user = user_repo.get(db, int(user_id))
    except Exception as e:
        print(f"DB Error in get_current_user: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    if user is None or not user.is_active:
        raise credentials_exception
    return user
