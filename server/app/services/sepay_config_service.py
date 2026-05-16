from dataclasses import dataclass
import logging

from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories.port_config_repository import port_config_repo
from app.services.sepay_api_client import SepayApiError, list_bank_accounts

logger = logging.getLogger('app.sepay.config')

SEPAY_CONFIG_KEYS = (
    'sepay_api_token',
    'sepay_sync_interval_sec',
    'sepay_cron_secret',
    'sepay_bank_account',
    'sepay_bank_name',
    'sepay_account_name',
)

SEPAY_CONFIG_DEFAULTS: dict[str, tuple[str, str]] = {
    'sepay_api_token': (
        '',
        'Bearer token API giao dịch từ my.sepay.vn (Tích hợp → API)',
    ),
    'sepay_sync_interval_sec': (
        '30',
        'Chu kỳ đồng bộ giao dịch SEPay (giây) khi server chạy nền',
    ),
    'sepay_cron_secret': (
        '',
        'Secret cho POST /api/v1/sepay/sync (cron hệ thống gọi kèm header X-Sepay-Cron-Secret)',
    ),
    'sepay_bank_account': ('', 'Số tài khoản nhận chuyển khoản (hiển thị QR)'),
    'sepay_bank_name': ('', 'Tên ngân hàng (VD: Vietcombank, BIDV)'),
    'sepay_account_name': ('', 'Tên chủ tài khoản'),
}


@dataclass(frozen=True)
class SepayConfig:
    api_token: str
    sync_interval_sec: int
    cron_secret: str
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
    interval_raw = _read_value(db, 'sepay_sync_interval_sec', str(settings.SEPAY_SYNC_INTERVAL_SEC))
    try:
        interval = max(15, int(interval_raw))
    except ValueError:
        interval = settings.SEPAY_SYNC_INTERVAL_SEC

    return SepayConfig(
        api_token=_read_value(db, 'sepay_api_token', settings.SEPAY_API_TOKEN),
        sync_interval_sec=interval,
        cron_secret=_read_value(db, 'sepay_cron_secret', settings.SEPAY_CRON_SECRET),
        bank_account=_read_value(db, 'sepay_bank_account', settings.SEPAY_BANK_ACCOUNT),
        bank_name=_read_value(db, 'sepay_bank_name', settings.SEPAY_BANK_NAME),
        account_name=_read_value(db, 'sepay_account_name', settings.SEPAY_ACCOUNT_NAME),
    )


@dataclass(frozen=True)
class ResolvedSepayBank:
    bank_account: str
    bank_name: str
    account_name: str
    source: str  # 'config' | 'api'


def resolve_sepay_bank(db: Session) -> ResolvedSepayBank | None:
    """Manual port_config first; else first active account from SEPay API."""
    cfg = get_sepay_config(db)
    account = cfg.bank_account.strip()
    bank = cfg.bank_name.strip()
    name = cfg.account_name.strip()
    if account and bank:
        return ResolvedSepayBank(
            bank_account=account,
            bank_name=bank,
            account_name=name,
            source='config',
        )

    if not cfg.api_token:
        return None

    try:
        accounts = list_bank_accounts(cfg.api_token, limit=20)
    except SepayApiError as exc:
        logger.warning('SEPay list bank accounts failed: %s', exc)
        return None

    active = [a for a in accounts if str(a.get('active', '1')) == '1']
    pool = active if active else accounts
    if not pool:
        return None

    picked = pool[0]
    api_account = str(picked.get('account_number') or '').strip()
    api_bank = str(picked.get('bank_short_name') or picked.get('bank_code') or '').strip()
    api_name = str(picked.get('account_holder_name') or picked.get('label') or '').strip()
    if not api_account or not api_bank:
        return None

    return ResolvedSepayBank(
        bank_account=api_account,
        bank_name=api_bank,
        account_name=api_name,
        source='api',
    )


def verify_cron_secret(db: Session, provided: str | None) -> bool:
    expected = get_sepay_config(db).cron_secret
    if not expected:
        return False
    return bool(provided) and provided.strip() == expected
