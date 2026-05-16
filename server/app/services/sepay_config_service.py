from dataclasses import dataclass
from typing import Optional

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories.port_config_repository import port_config_repo

SEPAY_CONFIG_KEYS = (
    'sepay_webhook_secret',
    'sepay_public_api_base_url',
    'sepay_bank_account',
    'sepay_bank_name',
    'sepay_account_name',
)

SEPAY_CONFIG_DEFAULTS: dict[str, tuple[str, str]] = {
    'sepay_webhook_secret': ('', 'Secret HMAC-SHA256 khi tạo webhook trên my.sepay.vn'),
    'sepay_public_api_base_url': (
        '',
        'URL gốc API backend công khai (VD: https://api.example.com). Để trống = lấy từ request khi gọi API.',
    ),
    'sepay_bank_account': ('', 'Số tài khoản nhận chuyển khoản (hiển thị QR)'),
    'sepay_bank_name': ('', 'Tên ngân hàng (VD: Vietcombank, BIDV)'),
    'sepay_account_name': ('', 'Tên chủ tài khoản'),
}


@dataclass(frozen=True)
class SepayConfig:
    webhook_secret: str
    bank_account: str
    bank_name: str
    account_name: str


def _read_value(db: Session, key: str, env_fallback: str) -> str:
    row = port_config_repo.get_by_key(db, key)
    if row is not None:
        stored = (row.value or '').strip()
        if stored:
            return stored
    return (env_fallback or '').strip()


def get_sepay_config(db: Session) -> SepayConfig:
    return SepayConfig(
        webhook_secret=_read_value(db, 'sepay_webhook_secret', settings.SEPAY_WEBHOOK_SECRET),
        bank_account=_read_value(db, 'sepay_bank_account', settings.SEPAY_BANK_ACCOUNT),
        bank_name=_read_value(db, 'sepay_bank_name', settings.SEPAY_BANK_NAME),
        account_name=_read_value(db, 'sepay_account_name', settings.SEPAY_ACCOUNT_NAME),
    )


def resolve_public_api_base(db: Session, request: Optional[Request] = None) -> str:
    stored = _read_value(db, 'sepay_public_api_base_url', settings.SEPAY_PUBLIC_API_BASE_URL)
    if stored:
        return stored.rstrip('/')
    if request is not None:
        return str(request.base_url).rstrip('/')
    return ''


def build_sepay_webhook_url(db: Session, request: Optional[Request] = None) -> str:
    base = resolve_public_api_base(db, request)
    if not base:
        return ''
    if base.endswith('/api/v1'):
        api_root = base
    else:
        api_root = f'{base}/api/v1'
    return f'{api_root.rstrip("/")}/sepay/webhook'
