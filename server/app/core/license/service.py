"""LicenseService — máy trạng thái license cục bộ (chưa gọi Keygate).

Task này chỉ gồm phần state/accessor: tính status hiệu lực từ row
``license_state``, cache snapshot trong RAM, kiểm tra máy có bị đổi không và
các helper enforcement. Việc activate/verify mạng nằm ở task sau; module này
không import HTTP client và không gọi mạng.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from app.core.config import settings
from app.core.license.features import max_cameras as registry_max_cameras
from app.core.license.features import normalize_features
from app.core.license.machine import resolve_machine_code
from app.db.session import SessionLocal
from app.models.license_state import LicenseState
from app.repositories.license_state_repository import license_state_repo
from app.utils.crypto import decrypt_secret

logger = logging.getLogger(__name__)

ENFORCEMENT_MODES = ('off', 'warn', 'enforce')
USABLE_STATUSES = frozenset({'valid', 'grace'})
_TERMINAL_STATUSES = frozenset({'suspended', 'revoked', 'expired', 'invalid'})
_DATE_BASED_STATUSES = frozenset({'active', 'trialing', 'past_due', 'valid', 'grace'})
_NOT_INITIALIZED = 'LicenseService not initialized'


def _as_utc(value: datetime) -> datetime:
    """Chuẩn hoá datetime về aware UTC (DB trả aware; test có thể truyền naive)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _initial_enforcement_mode() -> str:
    """Enforcement mặc định cho lần tạo row đầu tiên (env chỉ là default).

    ``settings.LICENSE_ENFORCEMENT`` đã được pydantic validate thành
    ``off|warn|enforce``; vẫn chuẩn hoá phòng khi test/override truyền giá trị
    lạ, fallback ``warn`` (an toàn, không tự bật chặn).
    """
    mode = str(getattr(settings, 'LICENSE_ENFORCEMENT', '') or '').strip().lower()
    return mode if mode in ENFORCEMENT_MODES else 'warn'


def compute_effective_status(
    *,
    has_key: bool,
    stored_status: str,
    valid_until: datetime | None,
    grace_days: int,
    now: datetime | None = None,
) -> str:
    """Tính trạng thái hiệu lực từ trạng thái lưu DB + hạn dùng.

    Thứ tự ưu tiên: chưa có key → ``unlicensed``; suspend/revoke (và các trạng
    thái kết thúc ``expired``/``invalid``) thắng ngay, không được grace; trạng
    thái lạ → ``invalid``. Còn lại hạn dùng quyết định ``valid`` → ``grace`` →
    ``expired``. Không có ``valid_until`` được coi là không hết hạn.
    """
    if not has_key:
        return 'unlicensed'

    status = str(stored_status or '').strip().lower()
    if status in _TERMINAL_STATUSES:
        return status
    if status not in _DATE_BASED_STATUSES:
        return 'invalid'
    if valid_until is None:
        return 'valid'

    moment = _as_utc(now) if now is not None else datetime.now(timezone.utc)
    expires_at = _as_utc(valid_until)
    if moment <= expires_at:
        return 'valid'

    grace = max(int(grace_days or 0), 0)
    if moment <= expires_at + timedelta(days=grace):
        return 'grace'
    return 'expired'


@dataclass(frozen=True)
class LicenseSnapshot:
    """Ảnh chụp bất biến của row ``license_state`` tại thời điểm refresh."""

    instance_id: str
    license_id: str | None
    plan_name: str | None
    status: str
    valid_until: datetime | None
    grace_days: int
    features: dict[str, Any]
    token: str | None
    token_exp: datetime | None
    pubkey: str | None
    last_verified_at: datetime | None
    last_error: str | None
    enforcement_mode: str
    # Nội bộ: row có ``license_key_enc`` hay không. Không phải field public của
    # snapshot (giữ đúng các field mirror row theo brief); mặc định False
    # (fail-closed) cho snapshot dựng thủ công không có ngữ cảnh row.
    _has_key: bool = field(default=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        # Chốt status hiệu lực ngay khi snapshot được tạo: thời gian trôi qua
        # không tự đổi status cho tới lần refresh/verify kế tiếp.
        object.__setattr__(
            self,
            '_effective_status',
            compute_effective_status(
                has_key=bool(self._has_key),
                stored_status=self.status,
                valid_until=self.valid_until,
                grace_days=self.grace_days,
            ),
        )

    @property
    def effective_status(self) -> str:
        return self._effective_status  # type: ignore[attr-defined]


class LicenseService:
    """Singleton giữ snapshot license và các accessor thuần (không HTTP)."""

    def __init__(self) -> None:
        self._snapshot: LicenseSnapshot | None = None
        self._machine_code = ''

    def initialize(self) -> None:
        """Nạp/tạo row license_state và chốt mã máy; không gọi mạng.

        - Có mã máy từ host/override: row mới lưu mã máy đó.
        - Không đọc được host identity: dùng ``instance_id`` đã lưu, chưa có
          thì sinh UUID và cảnh báo (fallback dev).
        - Mã máy khác ``instance_id`` đã lưu: đánh dấu ``invalid`` +
          ``last_error='machine changed'`` nhưng **không** ghi đè mã cũ; chỉ
          lần activate lại mới được đổi instance id.
        """
        computed = str(resolve_machine_code() or '').strip()
        db = SessionLocal()
        try:
            is_new = license_state_repo.get(db) is None
            if not computed:
                logger.warning(
                    'No readable host identity; using persisted license instance id fallback'
                )
                stored_id = self._stored_instance_id(db)
                resolved = stored_id or uuid4().hex
                row = license_state_repo.ensure(db, resolved)
                if not str(row.instance_id or '').strip():
                    row = license_state_repo.update(db, instance_id=resolved)
            else:
                row = license_state_repo.ensure(db, computed)
                stored_id = str(row.instance_id or '').strip()
                if not stored_id:
                    row = license_state_repo.update(db, instance_id=computed)
                elif stored_id != computed:
                    logger.warning(
                        'License machine code changed (stored=%s, computed=%s); '
                        'marking license invalid, re-activation required',
                        stored_id,
                        computed,
                    )
                    row = license_state_repo.update(
                        db,
                        status='invalid',
                        last_error='machine changed',
                    )

            # Env chỉ là default cho lần tạo row đầu tiên; các lần boot sau
            # tuyệt đối không ghi đè mode admin đã đổi runtime.
            if is_new:
                row = license_state_repo.update(
                    db, enforcement_mode=_initial_enforcement_mode()
                )

            db.commit()
            db.refresh(row)
            self._machine_code = computed or str(row.instance_id or '').strip()
            self._snapshot = self._build_snapshot(row)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _stored_instance_id(db) -> str:
        row = license_state_repo.get(db)
        return str(row.instance_id or '').strip() if row is not None else ''

    @staticmethod
    def _build_snapshot(row: LicenseState) -> LicenseSnapshot:
        status = str(row.status or '').strip().lower() or 'unlicensed'
        enforcement = str(row.enforcement_mode or '').strip().lower()
        if enforcement not in ENFORCEMENT_MODES:
            enforcement = 'warn'
        return LicenseSnapshot(
            instance_id=str(row.instance_id or '').strip(),
            license_id=row.license_id,
            plan_name=row.plan_name,
            status=status,
            valid_until=row.valid_until,
            grace_days=int(row.grace_days or 0),
            features=normalize_features(row.features or {}),
            token=row.token,
            token_exp=row.token_exp,
            pubkey=row.pubkey,
            last_verified_at=row.last_verified_at,
            last_error=row.last_error,
            enforcement_mode=enforcement,
            # `has_key` lấy từ chính row: status='active' nhưng thiếu
            # license_key_enc phải là unlicensed, không được fail-open.
            _has_key=bool(row.license_key_enc),
        )

    def snapshot(self) -> LicenseSnapshot:
        if self._snapshot is None:
            raise RuntimeError(_NOT_INITIALIZED)
        return self._snapshot

    def refresh_snapshot(self) -> LicenseSnapshot:
        """Đọc lại row từ DB và thay snapshot đang cache."""
        db = SessionLocal()
        try:
            row = license_state_repo.get(db)
            if row is None:
                raise RuntimeError('license_state row does not exist; call initialize() first')
            self._snapshot = self._build_snapshot(row)
            return self._snapshot
        finally:
            db.close()

    def machine_code(self) -> str:
        return self._machine_code

    def status(self) -> str:
        return self.snapshot().effective_status

    def is_usable(self) -> bool:
        return self.status() in USABLE_STATUSES

    def features(self) -> dict[str, Any]:
        return dict(self.snapshot().features)

    def max_cameras(self) -> int:
        return registry_max_cameras(self.features())

    def enforcement_mode(self) -> str:
        return self.snapshot().enforcement_mode

    def set_enforcement_mode(self, mode: str) -> None:
        normalized = str(mode or '').strip().lower()
        if normalized not in ENFORCEMENT_MODES:
            raise ValueError(
                f'invalid enforcement mode: {mode!r}; expected one of {ENFORCEMENT_MODES}'
            )
        self.snapshot()  # service phải initialize trước khi ghi DB
        db = SessionLocal()
        try:
            license_state_repo.update(db, enforcement_mode=normalized)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
        self.refresh_snapshot()

    def days_left(self) -> int | None:
        valid_until = self.snapshot().valid_until
        if valid_until is None:
            return None
        remaining = (_as_utc(valid_until) - datetime.now(timezone.utc)).total_seconds()
        if remaining <= 0:
            return 0
        return int(math.ceil(remaining / 86400))

    def license_key_hint(self) -> str | None:
        """4 ký tự cuối của license key (đã giải mã), ``None`` khi chưa có key."""
        if self.status() == 'unlicensed':
            return None
        db = SessionLocal()
        try:
            row = license_state_repo.get(db)
            if row is None or not row.license_key_enc:
                return None
            key = decrypt_secret(row.license_key_enc)
            if not key:
                return None
            return '****' + str(key)[-4:]
        finally:
            db.close()

    def should_block_new_behavior(self) -> bool:
        return self.enforcement_mode() == 'enforce' and not self.is_usable()


license_service = LicenseService()
