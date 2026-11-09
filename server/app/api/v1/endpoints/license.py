"""License API: status/activate/refresh/enforcement (admin-only trừ /status)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user, require_admin
from app.core.license.keygate_client import KeygateError, KeygateNetworkError
from app.core.license.service import license_service
from app.schemas.license import (
    LicenseActivateRequest,
    LicenseEnforcementUpdate,
    LicenseStatusRead,
)

router = APIRouter()

_NETWORK_ERROR_DETAIL = 'Không kết nối được license server'


def _status_payload() -> LicenseStatusRead:
    """Dựng payload từ snapshot; key chỉ trả về hint 4 ký tự cuối."""
    snapshot = license_service.snapshot()
    # `effective_status` là status đã tính cả hạn dùng/has_key; fallback cho
    # snapshot thay thế (test double) không có property này.
    effective_status = getattr(snapshot, 'effective_status', None) or snapshot.status
    return LicenseStatusRead(
        status=effective_status,
        plan_name=snapshot.plan_name,
        valid_until=snapshot.valid_until,
        days_left=license_service.days_left(),
        grace_days=snapshot.grace_days,
        features=dict(snapshot.features),
        enforcement_mode=snapshot.enforcement_mode,
        instance_id=snapshot.instance_id,
        machine_code=license_service.machine_code(),
        license_key_hint=license_service.license_key_hint(),
        last_verified_at=snapshot.last_verified_at,
        last_error=snapshot.last_error,
    )


@router.get('/status', response_model=LicenseStatusRead)
def get_license_status(_=Depends(get_current_user)):
    """FE gọi khi mount layout: quyết định màn hình nhập key + cảnh báo quota."""
    return _status_payload()


@router.get('/', response_model=LicenseStatusRead)
def get_license_state(_=Depends(require_admin)):
    """Cùng payload /status nhưng chỉ admin (ops xem đầy đủ)."""
    return _status_payload()


@router.post('/activate', response_model=LicenseStatusRead)
def activate_license(data: LicenseActivateRequest, _=Depends(require_admin)):
    """Kích hoạt key với Keygate rồi verify ngay; lỗi nghiệp vụ → 400, mạng → 503."""
    try:
        license_service.activate(data.license_key, label=data.label)
    except KeygateNetworkError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_NETWORK_ERROR_DETAIL,
        ) from exc
    except KeygateError as exc:
        # KeygateError không có thuộc tính `.message`; chỉ có `.code` + str(exc).
        code = exc.code or 'KEYGATE_ERROR'
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'{code}: {exc}',
        ) from exc
    return _status_payload()


@router.post('/refresh', response_model=LicenseStatusRead)
def refresh_license(_=Depends(require_admin)):
    """Verify lại với Keygate ngay (verify_now tự nuốt lỗi mạng và ghi last_error)."""
    license_service.verify_now()
    return _status_payload()


@router.put('/enforcement')
def update_enforcement(data: LicenseEnforcementUpdate, _=Depends(require_admin)):
    """Đổi enforcement mode runtime (ops qua curl/runbook, không có UI)."""
    license_service.set_enforcement_mode(data.mode)
    return {'mode': data.mode}
