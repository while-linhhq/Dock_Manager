"""Unit tests cho activate/verify Keygate + vòng check-in nền của LicenseService.

Mọi test dùng ``FakeClient`` — tuyệt đối không gọi mạng thật. Service tự
``commit`` nên fixture autouse lưu row ``license_state`` id=1 gốc (nếu có), xoá
trước test và khôi phục lại trong ``finally`` (giống
``test_license_service_state.py``), không đụng bảng khác.
"""
from __future__ import annotations

import asyncio
import base64
import json
import time
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.core.config import settings
from app.core.license import background as background_module
from app.core.license.keygate_client import KeygateClient, KeygateError, KeygateNetworkError
from app.core.license.service import LicenseService
from app.db.schema_patches import _ensure_license_state
from app.db.session import SessionLocal
from app.models.license_state import LicenseState
from app.repositories.license_state_repository import license_state_repo
from app.utils.crypto import decrypt_secret

TEST_LICENSE_KEY = 'DSIGHT-TEST-KEY'


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b'=').decode()


def _sign(payload: dict, key: Ed25519PrivateKey) -> str:
    encoded = _b64(json.dumps(payload).encode())
    return f'{encoded}.{_b64(key.sign(encoded.encode()))}'


def _keypair() -> tuple[Ed25519PrivateKey, str]:
    private_key = Ed25519PrivateKey.generate()
    public_hex = private_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    ).hex()
    return private_key, public_hex


class FakeClient:
    """Keygate client giả; chỉ ghi nhận lời gọi, không bao giờ chạm mạng."""

    def __init__(self) -> None:
        self.verify_calls = 0
        self.activate_calls = 0
        self.pubkey_calls = 0
        self.fail = None
        self.pubkey = '00' * 32
        self.activation: tuple[str, str, str] | None = None
        self.result: dict = {
            'status': 'active',
            'plan_name': 'Standard',
            'features': {'max_cameras': '12'},
            'valid_until': (datetime.now(timezone.utc) + timedelta(days=365)).isoformat(),
            'grace_days': 15,
        }

    def public_key(self) -> str:
        self.pubkey_calls += 1
        return self.pubkey

    def activate(self, key, identifier, label=''):
        self.activate_calls += 1
        self.activation = (key, identifier, label)
        if self.fail:
            raise self.fail
        return {'status': 'already_activated'}

    def verify(self, key, identifier):
        self.verify_calls += 1
        if self.fail:
            raise self.fail
        return self.result


@pytest.fixture(autouse=True)
def _isolated_license_state():
    """Để lại DB sạch: bảng đã tồn tại, chỉ row id=1 bị chạm."""
    _ensure_license_state()
    db = SessionLocal()
    try:
        original = db.get(LicenseState, 1)
        original_values = (
            {column.name: getattr(original, column.name) for column in LicenseState.__table__.columns}
            if original is not None
            else None
        )
        if original is not None:
            db.delete(original)
            db.commit()
    finally:
        db.close()

    try:
        yield
    finally:
        db = SessionLocal()
        try:
            row = db.get(LicenseState, 1)
            if row is not None:
                db.delete(row)
                db.commit()
            if original_values is not None:
                db.add(LicenseState(**original_values))
                db.commit()
        finally:
            db.close()


def _service(fake: FakeClient) -> LicenseService:
    svc = LicenseService(client=fake)
    svc.initialize()
    return svc


def _row() -> LicenseState | None:
    db = SessionLocal()
    try:
        return db.get(LicenseState, 1)
    finally:
        db.close()


# --- brief tests -----------------------------------------------------------


def test_verify_200_persists_features(tmp_path, monkeypatch):
    svc = _service(FakeClient())
    svc._persist_key('DSIGHT-TEST-KEY')
    out = svc.verify_now()
    assert out['status'] in {'valid', 'grace'}
    assert svc.max_cameras() == 12


def test_network_error_keeps_cached_state():
    fake = FakeClient()
    svc = _service(fake)
    svc._persist_key('DSIGHT-TEST-KEY')
    svc.verify_now()
    fake.fail = KeygateNetworkError('down')
    out = svc.verify_now()
    assert out['status'] in {'valid', 'grace'} and svc.max_cameras() == 12


def test_second_verify_overwrites_features():
    fake = FakeClient()
    svc = _service(fake)
    svc._persist_key('DSIGHT-TEST-KEY')
    svc.verify_now()
    fake.verify = lambda key, identifier: {
        'status': 'active',
        'plan_name': 'Standard',
        'features': {'max_cameras': '20'},
        'valid_until': None,
        'grace_days': 15,
    }
    svc.verify_now()
    assert svc.max_cameras() == 20  # last write wins, không trạng thái nửa vời


def test_verify_404_suspended():
    fake = FakeClient()
    svc = _service(fake)
    svc._persist_key('DSIGHT-TEST-KEY')
    svc.verify_now()
    fake.fail = KeygateError(404, 'LICENSE_NOT_FOUND')
    # activate phân loại thành suspended
    svc.client.activate = lambda *a, **k: (_ for _ in ()).throw(
        KeygateError(403, 'LICENSE_SUSPENDED')
    )
    out = svc.verify_now()
    assert out['status'] == 'suspended'


# --- activation ------------------------------------------------------------


def test_activate_persists_encrypted_key_and_verifies():
    fake = FakeClient()
    svc = _service(fake)

    out = svc.activate('KEYGATE-ACTIVATE-0001', label='port-a')

    assert fake.activate_calls == 1 and fake.verify_calls == 1
    assert fake.activation == ('KEYGATE-ACTIVATE-0001', svc.machine_code(), 'port-a')
    assert out['status'] in {'valid', 'grace'}
    row = _row()
    assert row is not None
    assert decrypt_secret(row.license_key_enc) == 'KEYGATE-ACTIVATE-0001'
    assert row.instance_id == svc.machine_code()


def test_activate_failure_does_not_persist_key():
    fake = FakeClient()
    svc = _service(fake)
    fake.fail = KeygateError(403, 'LICENSE_SUSPENDED')

    with pytest.raises(KeygateError):
        svc.activate('KEYGATE-NOT-SAVED')

    row = _row()
    assert row is not None and row.license_key_enc is None


# --- verify edge cases -----------------------------------------------------


def test_verify_without_key_is_unlicensed_without_network():
    fake = FakeClient()
    svc = _service(fake)

    out = svc.verify_now()

    assert out['status'] == 'unlicensed'
    assert fake.verify_calls == 0


def test_verify_200_without_token_sets_error_and_keeps_previous_token():
    fake = FakeClient()
    svc = _service(fake)
    svc._persist_key(TEST_LICENSE_KEY)
    db = SessionLocal()
    try:
        license_state_repo.update(
            db,
            token='previous-token',
            token_exp=datetime.now(timezone.utc) + timedelta(days=1),
            pubkey='ab' * 32,
        )
        db.commit()
    finally:
        db.close()

    out = svc.verify_now()

    assert out['status'] in {'valid', 'grace'}
    assert svc.max_cameras() == 12
    row = _row()
    assert row is not None
    assert row.token == 'previous-token'
    assert row.token_exp is not None
    assert row.last_error == 'verify response missing token'
    assert row.last_verified_at is not None


def test_verify_200_with_valid_signed_token_caches_exp_and_pubkey():
    private_key, public_hex = _keypair()
    fake = FakeClient()
    fake.pubkey = public_hex
    svc = _service(fake)
    svc._persist_key(TEST_LICENSE_KEY)
    exp = int(time.time()) + 3600
    token = _sign(
        {
            'lid': 'l1',
            'pid': 'p1',
            'pln': 'Standard',
            'sts': 'active',
            'did': svc.machine_code(),
            'ftr': {'max_cameras': '12'},
            'iat': int(time.time()),
            'exp': exp,
            'grc': 15,
            'nce': 'n1',
            'fpr': 'f' * 16,
        },
        private_key,
    )
    fake.result = {**fake.result, 'token': token}

    out = svc.verify_now()

    assert out['status'] in {'valid', 'grace'}
    row = _row()
    assert row is not None
    assert row.token == token and row.token_exp is not None
    assert int(row.token_exp.timestamp()) == exp
    assert row.pubkey == public_hex
    assert row.last_error is None


def test_verify_200_with_unverifiable_token_keeps_previous_token_and_sets_error():
    _, stored_public_hex = _keypair()
    private_key, _ = _keypair()  # token ký bằng key khác key đã cache
    fake = FakeClient()
    fake.pubkey = stored_public_hex
    svc = _service(fake)
    svc._persist_key(TEST_LICENSE_KEY)
    previous_exp = datetime.now(timezone.utc) + timedelta(days=2)
    db = SessionLocal()
    try:
        license_state_repo.update(
            db,
            token='previous-token',
            token_exp=previous_exp,
            pubkey=stored_public_hex,
        )
        db.commit()
    finally:
        db.close()
    token = _sign(
        {
            'lid': 'l1',
            'pid': 'p1',
            'pln': 'Standard',
            'sts': 'active',
            'did': svc.machine_code(),
            'ftr': {'max_cameras': '12'},
            'iat': int(time.time()),
            'exp': int(time.time()) + 3600,
            'grc': 15,
            'nce': 'n1',
            'fpr': 'f' * 16,
        },
        private_key,
    )
    fake.result = {**fake.result, 'token': token}

    out = svc.verify_now()

    assert out['status'] in {'valid', 'grace'}
    row = _row()
    assert row is not None
    assert row.token == 'previous-token'  # token mới không verify được → giữ token cũ
    assert row.token_exp is not None
    assert int(row.token_exp.timestamp()) == int(previous_exp.timestamp())
    assert row.last_error and 'token' in row.last_error
    assert svc.max_cameras() == 12


def test_verify_500_keeps_cached_state_and_sets_error():
    fake = FakeClient()
    svc = _service(fake)
    svc._persist_key(TEST_LICENSE_KEY)
    svc.verify_now()
    fake.fail = KeygateError(500, 'INTERNAL', None, 'boom')

    out = svc.verify_now()

    assert out['status'] in {'valid', 'grace'} and svc.max_cameras() == 12
    row = _row()
    assert row is not None and row.last_error is not None


def test_default_client_uses_settings():
    svc = LicenseService()

    assert isinstance(svc.client, KeygateClient)
    assert svc.client.base_url == settings.LICENSE_SERVER_URL.rstrip('/')
    assert svc.client.timeout == settings.LICENSE_HTTP_TIMEOUT_SEC


@pytest.mark.parametrize('remote_status', ['active', 'trialing', 'past_due'])
def test_verify_200_maps_active_like_statuses_to_stored_active(remote_status):
    fake = FakeClient()
    svc = _service(fake)
    svc._persist_key(TEST_LICENSE_KEY)
    fake.result = {**fake.result, 'status': remote_status, 'valid_until': None}

    out = svc.verify_now()

    assert out['status'] == 'valid'
    row = _row()
    assert row is not None and row.status == 'active'


def test_verify_404_activate_already_activated_keeps_previous_state():
    fake = FakeClient()
    svc = _service(fake)
    svc._persist_key(TEST_LICENSE_KEY)
    svc.verify_now()

    def _raise_404(key, identifier):
        raise KeygateError(404, 'LICENSE_NOT_FOUND')

    fake.verify = _raise_404
    out = svc.verify_now()

    assert out['status'] in {'valid', 'grace'}
    assert fake.activate_calls == 1
    row = _row()
    assert row is not None
    assert row.status == 'active'
    assert row.last_error == 'verify 404 but activate ok'


@pytest.mark.parametrize(
    ('activate_error', 'expected_status'),
    [
        (KeygateError(403, 'LICENSE_SUSPENDED'), 'suspended'),
        (KeygateError(403, 'LICENSE_REVOKED'), 'revoked'),
        (KeygateError(403, 'LICENSE_EXPIRED'), 'expired'),
        (KeygateError(403, 'LICENSE_CANCELED'), 'expired'),
        (KeygateError(403, 'SOMETHING_ELSE'), 'invalid'),
        (KeygateError(404, 'LICENSE_NOT_FOUND'), 'invalid'),
        (KeygateNetworkError('down'), 'invalid'),
    ],
    ids=['suspended', 'revoked', 'expired', 'canceled', 'unknown-code', '404', 'network'],
)
def test_verify_404_classifies_via_activate(activate_error, expected_status):
    fake = FakeClient()
    svc = _service(fake)
    svc._persist_key(TEST_LICENSE_KEY)
    svc.verify_now()
    fake.verify = lambda key, identifier: (_ for _ in ()).throw(
        KeygateError(404, 'LICENSE_NOT_FOUND')
    )
    svc.client.activate = lambda *a, **k: (_ for _ in ()).throw(activate_error)

    out = svc.verify_now()

    assert out['status'] == expected_status
    row = _row()
    assert row is not None and row.status == expected_status


# --- background loop -------------------------------------------------------


def test_background_checkin_calls_verify_and_stops(monkeypatch):
    calls: list[str] = []

    class _FakeService:
        def verify_now(self):
            calls.append('verify')
            return {'status': 'valid', 'features': {}}

    monkeypatch.setattr(background_module, 'license_service', _FakeService())
    monkeypatch.setattr(background_module.settings, 'LICENSE_CHECKIN_HOURS', 6)
    monkeypatch.setattr(background_module, '_task', None)

    async def scenario() -> None:
        background_module.start_license_background()
        first = background_module._task
        assert first is not None
        background_module.start_license_background()  # guard: không tạo task 2
        assert background_module._task is first
        for _ in range(200):
            if calls:
                break
            await asyncio.sleep(0.01)
        await background_module.stop_license_background()

    asyncio.run(scenario())

    assert calls == ['verify']
    assert background_module._task is None
