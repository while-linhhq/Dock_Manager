"""Route-level tests cho license API (Task 8).

Không chạm DB/Keygate thật: service singleton được thay bằng snapshot/stub trong
từng test, dependency ``get_current_user`` được override, và middleware audit
(ghi DB cho request mutating) được stub no-op.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.core.license import service as service_module
from app.core.license.keygate_client import KeygateError, KeygateNetworkError
from app.main import app

client = TestClient(app)


def _user(admin=False):
    return SimpleNamespace(
        id=1,
        username='admin' if admin else 'op',
        is_active=True,
        role=SimpleNamespace(
            role_name='admin' if admin else 'operator',
            permissions={'all': True} if admin else {},
        ),
    )


def _snapshot(**overrides):
    values = {
        'instance_id': 'inst-1',
        'status': 'valid',
        'plan_name': 'Standard',
        'valid_until': None,
        'grace_days': 15,
        'features': {'max_cameras': 12},
        'enforcement_mode': 'warn',
        'last_verified_at': None,
        'last_error': None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.fixture(autouse=True)
def _stub_audit_writes(monkeypatch):
    """POST/PUT đi qua audit middleware; stub để không ghi audit_logs thật."""
    from app import main as main_module

    monkeypatch.setattr(main_module.audit_log_repo, 'create', lambda *args, **kwargs: None)


@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    yield
    app.dependency_overrides.clear()


def _patch_status(monkeypatch, snapshot=None, days_left=365, hint='****1234'):
    monkeypatch.setattr(
        service_module.license_service,
        'snapshot',
        lambda: snapshot if snapshot is not None else _snapshot(),
    )
    monkeypatch.setattr(
        service_module.license_service, 'days_left', lambda snapshot=None: days_left
    )
    monkeypatch.setattr(service_module.license_service, 'machine_code', lambda: 'DSIGHT-TEST-0001')
    monkeypatch.setattr(
        service_module.license_service,
        'license_key_hint',
        lambda snapshot=None: hint,
    )


def test_status_requires_auth():
    assert client.get('/api/v1/license/status').status_code == 401


def test_status_returns_snapshot(monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: _user()
    monkeypatch.setattr(
        service_module.license_service,
        'snapshot',
        lambda: SimpleNamespace(
            instance_id='inst-1',
            status='valid',
            plan_name='Standard',
            valid_until=None,
            grace_days=15,
            features={'max_cameras': 12},
            enforcement_mode='warn',
            last_verified_at=None,
            last_error=None,
        ),
    )
    monkeypatch.setattr(service_module.license_service, 'days_left', lambda snapshot=None: 365)
    monkeypatch.setattr(
        service_module.license_service,
        'license_key_hint',
        lambda snapshot=None: '****1234',
        raising=False,
    )
    body = client.get('/api/v1/license/status').json()
    assert body['status'] == 'valid' and body['features'] == {'max_cameras': 12}
    app.dependency_overrides.clear()


def test_activate_forbidden_for_non_admin(monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: _user(admin=False)
    r = client.post('/api/v1/license/activate', json={'license_key': 'K'})
    assert r.status_code == 403
    assert r.json()['detail'] == 'Chỉ admin được thao tác license'
    app.dependency_overrides.clear()


def test_status_payload_has_machine_code_hint_and_days_left(monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: _user()
    _patch_status(monkeypatch)
    body = client.get('/api/v1/license/status').json()

    assert body['machine_code'] == 'DSIGHT-TEST-0001'
    assert body['license_key_hint'] == '****1234'
    assert body['days_left'] == 365
    assert body['instance_id'] == 'inst-1'
    assert body['grace_days'] == 15
    assert body['enforcement_mode'] == 'warn'
    assert 'license_key' not in body


def test_admin_state_endpoint_requires_admin(monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: _user(admin=False)

    response = client.get('/api/v1/license/')

    assert response.status_code == 403
    assert response.json()['detail'] == 'Chỉ admin được thao tác license'


def test_admin_state_endpoint_returns_snapshot(monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: _user(admin=True)
    _patch_status(monkeypatch)

    response = client.get('/api/v1/license/')

    assert response.status_code == 200
    assert response.json()['status'] == 'valid'


def test_admin_state_alias_without_trailing_slash_does_not_redirect(monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: _user(admin=True)
    _patch_status(monkeypatch)

    response = client.get('/api/v1/license', follow_redirects=False)

    assert response.status_code == 200
    assert response.json()['status'] == 'valid'


def test_status_payload_reads_snapshot_once(monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: _user()
    calls = []
    snapshot = _snapshot()
    monkeypatch.setattr(
        service_module.license_service,
        'snapshot',
        lambda: calls.append(True) or snapshot,
    )
    monkeypatch.setattr(service_module.license_service, 'days_left', lambda snapshot=None: 10)
    monkeypatch.setattr(
        service_module.license_service, 'license_key_hint', lambda snapshot=None: '****1234'
    )
    monkeypatch.setattr(service_module.license_service, 'machine_code', lambda: 'DSIGHT-TEST-0001')

    response = client.get('/api/v1/license/status')

    assert response.status_code == 200
    assert len(calls) == 1


def test_activate_calls_service_and_returns_status(monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: _user(admin=True)
    calls = {}

    def _fake_activate(license_key, *, label=''):
        calls['license_key'] = license_key
        calls['label'] = label
        return {'status': 'valid', 'features': {'max_cameras': 12}, 'last_error': None}

    monkeypatch.setattr(service_module.license_service, 'activate', _fake_activate)
    _patch_status(monkeypatch)

    response = client.post(
        '/api/v1/license/activate',
        json={'license_key': 'KEYGATE-TEST-ABCD-1234', 'label': 'Cảng Test'},
    )

    assert response.status_code == 200
    assert calls == {'license_key': 'KEYGATE-TEST-ABCD-1234', 'label': 'Cảng Test'}
    assert response.json()['status'] == 'valid'
    assert response.json()['license_key_hint'] == '****1234'


def test_activate_maps_keygate_business_error_to_400(monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: _user(admin=True)

    def _raise(*args, **kwargs):
        raise KeygateError(403, 'LICENSE_REVOKED', {'reason': 'revoked'}, 'license revoked')

    monkeypatch.setattr(service_module.license_service, 'activate', _raise)

    response = client.post('/api/v1/license/activate', json={'license_key': 'K'})

    assert response.status_code == 400
    assert response.json()['detail'] == 'LICENSE_REVOKED: license revoked'


def test_activate_maps_network_error_to_503(monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: _user(admin=True)

    def _raise(*args, **kwargs):
        raise KeygateNetworkError('timed out')

    monkeypatch.setattr(service_module.license_service, 'activate', _raise)

    response = client.post('/api/v1/license/activate', json={'license_key': 'K'})

    assert response.status_code == 503
    assert response.json()['detail'] == 'Không kết nối được license server'


def test_activate_returns_503_when_post_verify_status_not_usable(monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: _user(admin=True)
    monkeypatch.setattr(
        service_module.license_service,
        'activate',
        lambda key, label='': {'status': 'invalid', 'features': {}, 'last_error': 'boom'},
    )

    response = client.post('/api/v1/license/activate', json={'license_key': 'K'})

    assert response.status_code == 503
    assert response.json()['detail'] == (
        'Đã lưu license key nhưng chưa xác thực được license server. '
        'Vui lòng kiểm tra kết nối và thử lại.'
    )


def test_refresh_calls_verify_now_and_returns_status(monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: _user(admin=True)
    calls = []
    monkeypatch.setattr(
        service_module.license_service,
        'verify_now',
        lambda: calls.append(True) or {'status': 'valid', 'features': {}, 'last_error': None},
    )
    _patch_status(monkeypatch)

    response = client.post('/api/v1/license/refresh')

    assert response.status_code == 200
    assert calls == [True]
    assert response.json()['status'] == 'valid'


def test_enforcement_requires_admin(monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: _user(admin=False)

    response = client.put('/api/v1/license/enforcement', json={'mode': 'enforce'})

    assert response.status_code == 403
    assert response.json()['detail'] == 'Chỉ admin được thao tác license'


def test_enforcement_updates_mode(monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: _user(admin=True)
    modes = []
    monkeypatch.setattr(
        service_module.license_service, 'set_enforcement_mode', lambda mode: modes.append(mode)
    )

    response = client.put('/api/v1/license/enforcement', json={'mode': 'enforce'})

    assert response.status_code == 200
    assert response.json() == {'mode': 'enforce'}
    assert modes == ['enforce']


def test_enforcement_rejects_unknown_mode(monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: _user(admin=True)

    response = client.put('/api/v1/license/enforcement', json={'mode': 'bogus'})

    assert response.status_code == 422


def test_activate_requires_license_key(monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: _user(admin=True)

    response = client.post('/api/v1/license/activate', json={})

    assert response.status_code == 422
