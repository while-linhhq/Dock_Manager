"""Mã hoá bí mật lưu trong DB (license key) bằng Fernet.

Key Fernet dẫn xuất từ ``settings.SECRET_KEY`` (SHA-256 → base64 urlsafe) nên
không cần thêm biến môi trường riêng, và mọi instance dùng chung SECRET_KEY sẽ
giải mã được dữ liệu của nhau. Đổi SECRET_KEY làm ciphertext cũ không giải mã
được nữa — ``decrypt_secret`` trả ``None`` thay vì ném lỗi để nơi gọi coi như
chưa cấu hình và cho nhập lại key.
"""
from __future__ import annotations

import base64
import hashlib
from functools import lru_cache
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

@lru_cache(maxsize=1)
def _get_fernet() -> Fernet:
    """Fernet instance dựng từ SECRET_KEY của app (cache để khỏi hash mỗi lần)."""
    digest = hashlib.sha256(settings.SECRET_KEY.encode('utf-8')).digest()
    return Fernet(base64.urlsafe_b64encode(digest))

def encrypt_secret(value: str) -> str:
    """Mã hoá ``value`` thành token Fernet (str) để lưu DB."""
    return _get_fernet().encrypt(str(value or '').encode('utf-8')).decode('utf-8')

def decrypt_secret(token: str) -> Optional[str]:
    """Giải mã token Fernet; trả ``None`` nếu token hỏng/khác key (không ném lỗi)."""
    try:
        return _get_fernet().decrypt(str(token).encode('utf-8')).decode('utf-8')
    except InvalidToken:
        return None
    except Exception:
        return None
