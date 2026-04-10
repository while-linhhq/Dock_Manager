from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import jwt

from app.core.config import settings


def create_access_token(subject: str | int, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {'sub': str(subject), 'exp': expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
