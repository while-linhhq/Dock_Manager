from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.license.features import feature_bool
from app.core.license.service import license_service
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


def require_discount_approver(current_user=Depends(get_current_user)):
    from app.utils.rbac import can_approve_discount

    if not can_approve_discount(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Không có quyền duyệt giảm giá',
        )
    return current_user


def require_admin(current_user=Depends(get_current_user)):
    from app.utils.rbac import is_admin_user

    if not is_admin_user(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Chỉ admin được thao tác license',
        )
    return current_user


_LICENSE_BLOCKED_DETAIL = (
    'License không hợp lệ hoặc đã hết hạn. Không thể bắt đầu pipeline mới; '
    'pipeline đang chạy vẫn tiếp tục.'
)


def require_license_state() -> None:
    """Chặn hành vi mới khi license không dùng được (mode ``enforce``).

    Cố ý KHÔNG phụ thuộc ``get_current_user``: ``/pipeline/start`` không yêu
    cầu auth (dev autostart), và đây là điểm mở rộng cho router tương lai.
    """
    if license_service.should_block_new_behavior():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_LICENSE_BLOCKED_DETAIL,
        )


def require_module(module_key: str) -> Callable[[], None]:
    """Factory dependency chặn endpoint khi license không cấp ``module_key``.

    Chưa gắn vào router nào — điểm mở rộng cho các package/module sau này.
    ``feature_bool`` fail-closed: thiếu/sai kiểu đều coi là không có quyền.
    """

    def _require_module() -> None:
        if not feature_bool(license_service.features(), module_key):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f'Module {module_key} chưa được cấp trong license',
            )

    return _require_module
