"""Test enforcement quota camera (Task 9).

Không gọi mạng Keygate: ``max_cameras``/``enforcement_mode`` và số row camera
đều được monkeypatch để kết quả tất định. Chỉ row do test tạo (nhận diện qua
``rtsp_url`` riêng) mới bị xoá khỏi PostgreSQL dùng chung.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.core.license import service as service_module
from app.db.session import SessionLocal
from app.main import app
from app.models.camera import Camera

client = TestClient(app)

TEST_RTSP_URLS = ('rtsp://quota-test/1', 'rtsp://quota-warn/1')
EXPECTED_DETAIL = (
    'Đã đạt giới hạn {limit} camera của license (hiện có {current}). '
    'Liên hệ DTG để nâng giới hạn.'
)
LICENSE_BLOCKED_DETAIL = (
    'License không hợp lệ hoặc đã hết hạn. Không thể tạo camera mới; '
    'dữ liệu hiện có vẫn giữ nguyên.'
)


def _admin_user():
    return SimpleNamespace(
        id=1,
        username='admin',
        is_active=True,
        role=SimpleNamespace(role_name='admin', permissions={'all': True}),
    )


def _delete_test_camera_rows():
    """Xoá đúng các row test có thể đã tạo; không chạm dữ liệu khác."""
    db = SessionLocal()
    try:
        db.query(Camera).filter(Camera.rtsp_url.in_(TEST_RTSP_URLS)).delete(
            synchronize_session=False
        )
        db.commit()
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _stub_audit_writes(monkeypatch):
    """POST/DELETE đi qua audit middleware; stub để không ghi audit_logs thật."""
    from app import main as main_module

    monkeypatch.setattr(main_module.audit_log_repo, 'create', lambda *args, **kwargs: None)


@pytest.fixture(autouse=True)
def _clean_test_camera_rows():
    _delete_test_camera_rows()
    yield
    app.dependency_overrides.clear()
    _delete_test_camera_rows()


@pytest.fixture(autouse=True)
def _license_usable_by_default(monkeypatch):
    """Các test quota cũ không quan tâm license state; mặc định cho usable."""
    monkeypatch.setattr(
        service_module.license_service, 'should_block_new_behavior', lambda: False
    )


def _override(monkeypatch, limit=1, mode='enforce', current=1, block=False):
    app.dependency_overrides[get_current_user] = lambda: _admin_user()
    monkeypatch.setattr(service_module.license_service, 'max_cameras', lambda: limit)
    monkeypatch.setattr(service_module.license_service, 'enforcement_mode', lambda: mode)
    monkeypatch.setattr(
        service_module.license_service, 'should_block_new_behavior', lambda: block
    )
    from app.core.license import enforcement

    monkeypatch.setattr(enforcement.camera_repo, 'count_all', lambda db: current)


def test_create_camera_blocked_at_limit(monkeypatch):
    _override(monkeypatch, limit=1, mode='enforce')
    r = client.post(
        '/api/v1/cameras/',
        json={'camera_name': 'quota-test', 'rtsp_url': 'rtsp://quota-test/1', 'is_active': False},
    )
    assert r.status_code == 403 and 'giới hạn' in r.json()['detail']


def test_create_camera_blocked_by_unusable_license_before_quota(monkeypatch):
    """Enforce + license unusable: 403 license detail, kể cả khi còn slot."""
    _override(monkeypatch, limit=12, mode='enforce', current=3, block=True)
    r = client.post(
        '/api/v1/cameras/',
        json={'camera_name': 'quota-test', 'rtsp_url': 'rtsp://quota-test/1', 'is_active': False},
    )

    assert r.status_code == 403
    assert r.json()['detail'] == LICENSE_BLOCKED_DETAIL
    assert 'giới hạn' not in r.json()['detail']


def test_create_camera_allowed_in_warn(monkeypatch):
    _override(monkeypatch, limit=0, mode='warn')
    r = client.post(
        '/api/v1/cameras/',
        json={'camera_name': 'quota-warn', 'rtsp_url': 'rtsp://quota-warn/1', 'is_active': False},
    )
    assert r.status_code == 201
    client.delete(f"/api/v1/cameras/{r.json()['id']}")


def test_create_camera_blocked_detail_is_exact(monkeypatch):
    _override(monkeypatch, limit=1, mode='enforce', current=1)
    r = client.post(
        '/api/v1/cameras/',
        json={'camera_name': 'quota-test', 'rtsp_url': 'rtsp://quota-test/1', 'is_active': False},
    )

    assert r.status_code == 403
    assert r.json()['detail'] == EXPECTED_DETAIL.format(limit=1, current=1)


def test_check_camera_quota_allows_under_limit(monkeypatch):
    from app.core.license import enforcement

    monkeypatch.setattr(service_module.license_service, 'max_cameras', lambda: 5)
    monkeypatch.setattr(service_module.license_service, 'enforcement_mode', lambda: 'enforce')
    monkeypatch.setattr(enforcement.camera_repo, 'count_all', lambda db: 4)

    enforcement.check_camera_quota(None)  # không raise


def test_check_camera_quota_raises_at_limit(monkeypatch):
    from app.core.license import enforcement

    monkeypatch.setattr(service_module.license_service, 'max_cameras', lambda: 2)
    monkeypatch.setattr(service_module.license_service, 'enforcement_mode', lambda: 'enforce')
    monkeypatch.setattr(enforcement.camera_repo, 'count_all', lambda db: 2)

    with pytest.raises(enforcement.CameraLimitExceeded) as ei:
        enforcement.check_camera_quota(None)

    assert ei.value.limit == 2
    assert ei.value.current == 2


def test_check_camera_quota_warn_logs_and_allows(monkeypatch, caplog):
    from app.core.license import enforcement

    monkeypatch.setattr(service_module.license_service, 'max_cameras', lambda: 1)
    monkeypatch.setattr(service_module.license_service, 'enforcement_mode', lambda: 'warn')
    monkeypatch.setattr(enforcement.camera_repo, 'count_all', lambda db: 3)

    with caplog.at_level(logging.WARNING):
        enforcement.check_camera_quota(None)  # không raise

    assert 'license camera quota exceeded: 3/1 (warn mode)' in caplog.text


def test_check_camera_quota_mode_off_allows(monkeypatch):
    from app.core.license import enforcement

    monkeypatch.setattr(service_module.license_service, 'max_cameras', lambda: 0)
    monkeypatch.setattr(service_module.license_service, 'enforcement_mode', lambda: 'off')
    monkeypatch.setattr(enforcement.camera_repo, 'count_all', lambda db: 7)

    enforcement.check_camera_quota(None)  # không raise


def test_camera_quota_snapshot_returns_current_and_limit(monkeypatch):
    from app.core.license import enforcement

    monkeypatch.setattr(service_module.license_service, 'max_cameras', lambda: 12)
    monkeypatch.setattr(enforcement.camera_repo, 'count_all', lambda db: 3)

    assert enforcement.camera_quota_snapshot(None) == (3, 12)
