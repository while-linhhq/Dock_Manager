"""LicenseService — máy trạng thái + orchestration license Keygate.

Bao gồm: tính status hiệu lực từ row ``license_state``, cache snapshot trong
RAM, kiểm tra máy có bị đổi không, các helper enforcement, và phần gọi mạng
``activate``/``verify`` với Keygate. HTTP client được inject qua constructor
(``LicenseService(client=...)``) nên test không cần chạm mạng thật; token
license được verify offline bằng Ed25519 với public key cache trong DB.
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
from app.core.license.keygate_client import KeygateClient, KeygateError, KeygateNetworkError
from app.core.license.machine import resolve_machine_code
from app.core.license.token import LicenseTokenError, verify_license_token
from app.db.session import SessionLocal
from app.models.license_state import LicenseState
from app.repositories.license_state_repository import license_state_repo
from app.utils.crypto import decrypt_secret, encrypt_secret

logger = logging.getLogger(__name__)

ENFORCEMENT_MODES = ('off', 'warn', 'enforce')
USABLE_STATUSES = frozenset({'valid', 'grace'})
_TERMINAL_STATUSES = frozenset({'suspended', 'revoked', 'expired', 'invalid'})
_DATE_BASED_STATUSES = frozenset({'active', 'trialing', 'past_due', 'valid', 'grace'})
_NOT_INITIALIZED = 'LicenseService not initialized'

# Keygate verify trả các trạng thái này khi license còn dùng được; DB chỉ lưu
# một trạng thái trung tính 'active', hạn dùng (valid_until/grace_days) quyết
# định valid/grace/expired. Các trạng thái khác giữ nguyên để hiển thị đúng.
_VERIFY_ACTIVE_STATUSES = frozenset({'active', 'trialing', 'past_due'})
_STATUS_BY_ACTIVATE_CODE = {
    'LICENSE_SUSPENDED': 'suspended',
    'LICENSE_REVOKED': 'revoked',
    'LICENSE_EXPIRED': 'expired',
    'LICENSE_CANCELED': 'expired',
}


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


def _parse_iso_datetime(value: Any) -> datetime | None:
    """Parse mốc thời gian ISO-8601 từ Keygate (chấp nhận hậu tố ``Z``).

    Giá trị thiếu/rỗng/không parse được trả ``None`` — service coi như license
    không đặt hạn, không để dữ liệu lỗi làm crash vòng verify.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        return _as_utc(value)
    text = str(value).strip()
    if not text:
        return None
    if text.endswith(('Z', 'z')):
        text = text[:-1] + '+00:00'
    try:
        return _as_utc(datetime.fromisoformat(text))
    except ValueError:
        return None


def _as_int(value: Any, default: int = 0) -> int:
    """Ép ``value`` sang int; ``bool``/giá trị hỏng rơi về ``default``."""
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _stored_status_from_verify(raw: Any) -> str:
    """Chuyển status của verify 200 sang status lưu DB.

    ``active|trialing|past_due`` đều lưu ``active``; status khác (nếu có) giữ
    nguyên chữ thường để ``compute_effective_status`` xử lý (status lạ →
    ``invalid``, fail closed). Thiếu status nhưng verify 200 → ``active``.
    """
    status = str(raw or '').strip().lower()
    if not status:
        return 'active'
    if status in _VERIFY_ACTIVE_STATUSES:
        return 'active'
    return status


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
    """Singleton giữ snapshot license, gọi Keygate và các accessor enforcement."""

    def __init__(self, client: KeygateClient | None = None) -> None:
        # Client injectable: production dùng KeygateClient thật, test dùng fake
        # để không bao giờ gọi mạng. Constructor client không thực hiện HTTP.
        self.client = client if client is not None else KeygateClient(
            settings.LICENSE_SERVER_URL,
            settings.LICENSE_HTTP_TIMEOUT_SEC,
        )
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

    # --- Keygate activation/verify -----------------------------------------

    def activate(self, license_key: str, *, label: str = '') -> dict[str, Any]:
        """Kích hoạt key với Keygate, lưu key đã mã hoá rồi verify ngay.

        Key chỉ được lưu sau khi activate thành công. Lỗi Keygate/mạng được ném
        nguyên cho endpoint xử lý (Task 8 map sang HTTP 400/503).
        """
        key = str(license_key or '')
        self.client.activate(key, self.machine_code(), label)
        self._persist_key(key)
        return self.verify_now()

    def verify_now(self) -> dict[str, Any]:
        """Gọi Keygate verify và áp kết quả vào row ``license_state``.

        Không ném lỗi mạng/nghiệp vụ: lỗi tạm thời giữ nguyên snapshot đã cache
        (chỉ ghi ``last_error``), verify 404 được phân loại qua ``activate``.
        Trả ``{'status', 'features', 'last_error'}`` với ``status`` là trạng
        thái hiệu lực ngay sau lần verify.
        """
        license_key = self._decrypt_license_key()
        if not license_key:
            return self._result()

        try:
            data = self.client.verify(license_key, self.machine_code())
        except KeygateNetworkError as exc:
            return self._record_error(f'verify network error: {exc}')
        except KeygateError as exc:
            if exc.status == 404:
                return self._classify_verify_404(license_key)
            detail = exc.code or str(exc) or 'unknown'
            return self._record_error(f'verify failed (HTTP {exc.status}): {detail}')
        return self._apply_verify_data(data)

    def _apply_verify_data(self, data: dict[str, Any]) -> dict[str, Any]:
        """Áp response verify 200 vào DB; token hỏng/thiếu không xoá features."""
        payload = data if isinstance(data, dict) else {}
        now = datetime.now(timezone.utc)
        raw_token = payload.get('token')
        token = raw_token.strip() if isinstance(raw_token, str) and raw_token.strip() else None

        # 200 là server xác nhận license dùng được: luôn cập nhật metadata +
        # features + hạn dùng; token chỉ cập nhật khi verify offline thành công.
        fields: dict[str, Any] = {
            'status': _stored_status_from_verify(payload.get('status')),
            'license_id': payload.get('license_id'),
            'plan_name': payload.get('plan_name'),
            'valid_until': _parse_iso_datetime(payload.get('valid_until')),
            'grace_days': _as_int(payload.get('grace_days'), 0),
            'features': normalize_features(payload.get('features') or {}),
            'last_verified_at': now,
        }
        last_error = None
        if token is None:
            # Giữ token cũ (nếu có) để offline cache không bị xoá bởi response
            # thiếu token; features/valid_until vẫn được cập nhật bình thường.
            last_error = 'verify response missing token'
        else:
            pubkey = self._stored_pubkey()
            if not pubkey:
                pubkey = self._fetch_public_key()
            if not pubkey:
                # Không verify được token → giữ token/token_exp cũ, chỉ báo lỗi.
                last_error = 'token verify failed: missing Keygate public key'
            else:
                try:
                    claims = verify_license_token(
                        token,
                        pubkey,
                        expected_identifier=self.machine_code(),
                        now=now,
                    )
                except LicenseTokenError as exc:
                    # Token không verify được: giữ token cũ (nếu có), không tin
                    # ``exp`` của token mới; features/valid_until vẫn đã cập nhật.
                    last_error = f'token verify failed: {exc}'
                else:
                    fields['token'] = token
                    fields['token_exp'] = datetime.fromtimestamp(claims.exp, tz=timezone.utc)
                    fields['pubkey'] = pubkey

        fields['last_error'] = last_error
        self._persist_fields(fields)
        return self._result()

    def _classify_verify_404(self, license_key: str) -> dict[str, Any]:
        """Verify 404 là câu trả lời dứt khoát — dùng activate để biết lý do.

        403 kèm code map sang suspended/revoked/expired; activate lỗi khác hoặc
        không kết nối được → ``invalid``. Activate thành công (máy đã activate
        trước đó) nghĩa là license vẫn dùng được: giữ nguyên trạng thái cũ.
        """
        try:
            self.client.activate(license_key, self.machine_code())
        except KeygateNetworkError as exc:
            return self._persist_classified('invalid', f'verify 404; activate unreachable: {exc}')
        except KeygateError as exc:
            if exc.status == 403:
                status = _STATUS_BY_ACTIVATE_CODE.get(str(exc.code or '').upper(), 'invalid')
                detail = exc.code or 'HTTP 403'
                return self._persist_classified(status, f'verify 404; activate: {detail}')
            return self._persist_classified(
                'invalid', f'verify 404; activate failed (HTTP {exc.status})'
            )
        return self._record_error('verify 404 but activate ok')

    def _record_error(self, message: str) -> dict[str, Any]:
        """Ghi ``last_error`` nhưng giữ nguyên status/features đã cache."""
        logger.warning('License verify error (giữ trạng thái cache): %s', message)
        self._persist_fields({'last_error': message})
        return self._result()

    def _persist_classified(self, status: str, message: str) -> dict[str, Any]:
        self._persist_fields({'status': status, 'last_error': message})
        return self._result()

    def _persist_key(self, license_key: str) -> None:
        """Lưu key đã mã hoá + ``instance_id`` hiện tại (helper của activate/test)."""
        fields: dict[str, Any] = {'license_key_enc': encrypt_secret(str(license_key or ''))}
        machine_code = self.machine_code()
        if machine_code:
            fields['instance_id'] = machine_code
        self._persist_fields(fields)

    def _persist_fields(self, fields: dict[str, Any]) -> None:
        """Cập nhật row id=1 rồi commit; lỗi rollback và ném lại cho caller."""
        db = SessionLocal()
        try:
            row = license_state_repo.get(db)
            if row is None:
                raise RuntimeError('license_state row does not exist; call initialize() first')
            license_state_repo.update(db, **fields)
            db.commit()
            db.refresh(row)
            snapshot = self._build_snapshot(row)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
        self._snapshot = snapshot

    def _decrypt_license_key(self) -> str | None:
        """Đọc + giải mã key trong DB; thiếu/hỏng (SECRET_KEY đổi) trả ``None``."""
        db = SessionLocal()
        try:
            row = license_state_repo.get(db)
            if row is None or not row.license_key_enc:
                return None
            key = decrypt_secret(row.license_key_enc)
        finally:
            db.close()
        if not key:
            logger.warning('Stored license key cannot be decrypted; treating as unlicensed')
        return key

    def _stored_pubkey(self) -> str:
        db = SessionLocal()
        try:
            row = license_state_repo.get(db)
            return str(row.pubkey or '').strip() if row is not None else ''
        finally:
            db.close()

    def _fetch_public_key(self) -> str:
        """Lấy pubkey Keygate; lỗi mạng/response hỏng chỉ log, token bị đánh lỗi."""
        try:
            pubkey = self.client.public_key()
        except Exception as exc:  # response lỗi không được làm sập verify 200
            logger.warning('Cannot fetch Keygate public key: %s', exc)
            return ''
        return str(pubkey or '').strip()

    def _result(self) -> dict[str, Any]:
        """Payload gọn trả cho caller (status hiệu lực + features đã chuẩn hoá)."""
        snapshot = self.snapshot()
        return {
            'status': self.status(),
            'features': dict(snapshot.features),
            'last_error': snapshot.last_error,
        }

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
