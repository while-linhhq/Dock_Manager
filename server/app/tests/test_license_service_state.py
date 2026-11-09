"""Unit tests cho pure status function + LicenseService state machine.

DB test dùng PostgreSQL thật (``license_state`` đã tồn tại) nhưng mỗi test được
cô lập: fixture lưu lại row gốc (nếu có), xoá row trước test rồi khôi phục sau
test — service commit nên không thể chỉ dựa vào rollback.
"""
from __future__ import annotations

import logging
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.core.license import service as service_module
from app.core.license.service import (
    LicenseService,
    LicenseSnapshot,
    compute_effective_status,
)
from app.db.schema_patches import _ensure_license_state
from app.db.session import SessionLocal
from app.models.license_state import LicenseState
from app.repositories.license_state_repository import license_state_repo
from app.utils.crypto import encrypt_secret

NOW = datetime(2026, 11, 9, tzinfo=timezone.utc)
MACHINE_CODE = 'DSIGHT-TEST-0001'
TEST_LICENSE_KEY = 'KEYGATE-TEST-ABCD-1234'


def _now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def _isolated_license_state():
    """Để lại DB sạch: bảng đã tồn tại, không đụng bảng khác."""
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


def _service(monkeypatch, code: str = MACHINE_CODE) -> LicenseService:
    monkeypatch.setattr(service_module, 'resolve_machine_code', lambda: code)
    return LicenseService()


def _seed_row(instance_id: str = 'DSIGHT-OLD-0000', **fields) -> None:
    # Row active/valid/grace phải có license key thì mới thực sự usable; fixture
    # tự gắn key để test đúng ngữ cảnh row thật. Truyền license_key_enc=None
    # khi cần test trường hợp active nhưng thiếu key.
    if 'license_key_enc' not in fields and str(fields.get('status') or '').lower() in {
        'active',
        'valid',
        'grace',
        'trialing',
        'past_due',
    }:
        fields['license_key_enc'] = encrypt_secret(TEST_LICENSE_KEY)
    db = SessionLocal()
    try:
        license_state_repo.ensure(db, instance_id)
        if fields:
            license_state_repo.update(db, **fields)
        db.commit()
    finally:
        db.close()


def _row() -> LicenseState | None:
    db = SessionLocal()
    try:
        return db.get(LicenseState, 1)
    finally:
        db.close()


def _snapshot_kwargs(**overrides):
    values = {
        'instance_id': MACHINE_CODE,
        'license_id': None,
        'plan_name': None,
        'status': 'active',
        'valid_until': None,
        'grace_days': 0,
        'features': {},
        'token': None,
        'token_exp': None,
        'pubkey': None,
        'last_verified_at': None,
        'last_error': None,
        'enforcement_mode': 'warn',
        '_has_key': True,
    }
    values.update(overrides)
    return values


# --- pure function ---------------------------------------------------------


def test_status_rules():
    assert compute_effective_status(has_key=False, stored_status='active', valid_until=None, grace_days=0, now=NOW) == 'unlicensed'
    assert compute_effective_status(has_key=True, stored_status='active', valid_until=NOW + timedelta(days=1), grace_days=15, now=NOW) == 'valid'
    assert compute_effective_status(has_key=True, stored_status='active', valid_until=NOW - timedelta(days=1), grace_days=15, now=NOW) == 'grace'
    assert compute_effective_status(has_key=True, stored_status='active', valid_until=NOW - timedelta(days=16), grace_days=15, now=NOW) == 'expired'
    assert compute_effective_status(has_key=True, stored_status='suspended', valid_until=NOW + timedelta(days=1), grace_days=15, now=NOW) == 'suspended'
    assert compute_effective_status(has_key=True, stored_status='revoked', valid_until=None, grace_days=0, now=NOW) == 'revoked'
    assert compute_effective_status(has_key=True, stored_status='weird', valid_until=None, grace_days=0, now=NOW) == 'invalid'


def test_status_grace_boundary_is_inclusive():
    assert compute_effective_status(
        has_key=True,
        stored_status='active',
        valid_until=NOW - timedelta(days=15),
        grace_days=15,
        now=NOW,
    ) == 'grace'
    assert compute_effective_status(
        has_key=True,
        stored_status='active',
        valid_until=NOW - timedelta(days=15, seconds=1),
        grace_days=15,
        now=NOW,
    ) == 'expired'


def test_status_no_key_wins_over_terminal_status():
    assert compute_effective_status(
        has_key=False,
        stored_status='suspended',
        valid_until=NOW + timedelta(days=1),
        grace_days=15,
        now=NOW,
    ) == 'unlicensed'


def test_status_valid_without_valid_until():
    assert compute_effective_status(
        has_key=True,
        stored_status='active',
        valid_until=None,
        grace_days=0,
        now=NOW,
    ) == 'valid'


def test_status_terminal_invalid_is_never_revived_by_dates():
    assert compute_effective_status(
        has_key=True,
        stored_status='invalid',
        valid_until=NOW + timedelta(days=365),
        grace_days=15,
        now=NOW,
    ) == 'invalid'


def test_snapshot_effective_status_is_computed_when_created():
    snap = LicenseSnapshot(**_snapshot_kwargs())
    assert snap.status == 'active'
    assert snap.effective_status == 'valid'
    with pytest.raises(FrozenInstanceError):
        snap.status = 'unlicensed'


# --- service ---------------------------------------------------------------


def test_snapshot_lazily_initializes(monkeypatch):
    """``snapshot()`` tự gọi initialize một lần khi service chưa init."""
    svc = _service(monkeypatch)
    assert svc.is_initialized() is False

    snap = svc.snapshot()

    assert svc.is_initialized() is True
    assert snap.instance_id == MACHINE_CODE
    assert snap.effective_status == 'unlicensed'


def test_snapshot_falls_back_when_initialize_fails(monkeypatch):
    """DB lỗi khi init không được làm /status/camera gate ném 500."""
    svc = _service(monkeypatch)

    def _boom(db):
        raise RuntimeError('db unavailable')

    monkeypatch.setattr(service_module.license_state_repo, 'get', _boom)

    snap = svc.snapshot()

    assert snap.effective_status == 'unlicensed'
    assert snap.last_error == 'license service unavailable'
    assert svc.status() == 'unlicensed'
    assert svc.is_usable() is False
    assert svc.enforcement_mode() == service_module._initial_enforcement_mode()
    assert svc.snapshot().last_error == 'license service unavailable'
    assert svc.is_initialized() is False


def test_initialize_creates_row_and_snapshot(monkeypatch):
    svc = _service(monkeypatch)
    svc.initialize()

    assert svc.machine_code() == MACHINE_CODE
    snap = svc.snapshot()
    assert snap.instance_id == MACHINE_CODE
    assert snap.status == 'unlicensed'
    assert snap.effective_status == 'unlicensed'
    assert snap.enforcement_mode == 'warn'
    assert svc.is_usable() is False

    row = _row()
    assert row is not None and row.instance_id == MACHINE_CODE
    assert row.status == 'unlicensed' and row.enforcement_mode == 'warn'


def test_initialize_is_idempotent(monkeypatch):
    svc = _service(monkeypatch)
    svc.initialize()
    svc.initialize()

    db = SessionLocal()
    try:
        assert db.query(LicenseState).count() == 1
    finally:
        db.close()
    assert svc.snapshot().instance_id == MACHINE_CODE


@pytest.mark.parametrize('mode', ['enforce', 'off'])
def test_initialize_seeds_enforcement_mode_from_settings_on_fresh_row(monkeypatch, mode):
    monkeypatch.setattr(
        service_module.settings, 'LICENSE_ENFORCEMENT', mode, raising=False
    )
    svc = _service(monkeypatch)
    svc.initialize()

    assert svc.enforcement_mode() == mode
    row = _row()
    assert row is not None and row.enforcement_mode == mode


def test_initialize_preserves_admin_set_enforcement_mode_on_later_boots(monkeypatch):
    monkeypatch.setattr(
        service_module.settings, 'LICENSE_ENFORCEMENT', 'enforce', raising=False
    )
    first = _service(monkeypatch)
    first.initialize()
    first.set_enforcement_mode('off')  # admin đổi runtime, không sửa .env

    # Env đổi giữa hai lần boot cũng không được ghi đè mode đã lưu trong DB.
    monkeypatch.setattr(
        service_module.settings, 'LICENSE_ENFORCEMENT', 'warn', raising=False
    )
    second = _service(monkeypatch)
    second.initialize()

    assert second.enforcement_mode() == 'off'
    row = _row()
    assert row is not None and row.enforcement_mode == 'off'


def test_initialize_falls_back_to_persisted_uuid(monkeypatch, caplog):
    monkeypatch.setattr(service_module, 'resolve_machine_code', lambda: '')
    svc = LicenseService()
    with caplog.at_level(logging.WARNING):
        svc.initialize()

    code = svc.machine_code()
    assert len(code) == 32
    UUID(code)  # không phải chuỗi rỗng/không hợp lệ
    assert svc.snapshot().instance_id == code
    assert 'host identity' in caplog.text.lower()

    # Lần khởi động sau dùng lại UUID đã lưu (không sinh mã mới).
    svc_again = LicenseService()
    svc_again.initialize()
    assert svc_again.machine_code() == code
    assert svc_again.snapshot().instance_id == code


def test_initialize_marks_machine_change_without_overwriting_stored_id(monkeypatch):
    _seed_row(status='active', valid_until=_now() + timedelta(days=30))

    svc = _service(monkeypatch, code='DSIGHT-NEW-0002')
    svc.initialize()

    snap = svc.snapshot()
    assert snap.instance_id == 'DSIGHT-OLD-0000'
    assert svc.machine_code() == 'DSIGHT-NEW-0002'
    assert snap.status == 'invalid'
    assert snap.effective_status == 'invalid'
    assert snap.last_error == 'machine changed'

    row = _row()
    assert row is not None and row.instance_id == 'DSIGHT-OLD-0000'
    assert row.status == 'invalid' and row.last_error == 'machine changed'


def test_initialize_keeps_state_when_machine_matches(monkeypatch):
    _seed_row('DSIGHT-SAME-0003', status='active', valid_until=_now() + timedelta(days=30))

    svc = _service(monkeypatch, code='DSIGHT-SAME-0003')
    svc.initialize()

    snap = svc.snapshot()
    assert snap.instance_id == 'DSIGHT-SAME-0003'
    assert snap.status == 'active'
    assert snap.last_error is None
    assert svc.status() == 'valid'


def test_active_row_without_license_key_reports_unlicensed(monkeypatch):
    _seed_row(
        MACHINE_CODE,
        status='active',
        valid_until=_now() + timedelta(days=30),
        license_key_enc=None,
    )
    svc = _service(monkeypatch)
    svc.initialize()

    snap = svc.snapshot()
    assert snap.status == 'active'
    assert snap.effective_status == 'unlicensed'
    assert svc.status() == 'unlicensed'
    assert svc.is_usable() is False


def test_machine_change_without_license_key_reports_unlicensed(monkeypatch):
    _seed_row(
        status='active',
        valid_until=_now() + timedelta(days=30),
        license_key_enc=None,
    )

    svc = _service(monkeypatch, code='DSIGHT-NEW-0002')
    svc.initialize()

    snap = svc.snapshot()
    assert snap.instance_id == 'DSIGHT-OLD-0000'
    assert snap.status == 'invalid'
    assert snap.last_error == 'machine changed'
    assert snap.effective_status == 'unlicensed'
    assert svc.status() == 'unlicensed'


def test_snapshot_status_is_normalized_to_lowercase(monkeypatch):
    _seed_row(
        MACHINE_CODE,
        status='ACTIVE',
        valid_until=_now() + timedelta(days=30),
    )
    svc = _service(monkeypatch)
    svc.initialize()

    snap = svc.snapshot()
    assert snap.status == 'active'
    assert snap.effective_status == 'valid'


def test_snapshot_is_cached_until_refresh(monkeypatch):
    _seed_row(
        MACHINE_CODE,
        status='active',
        valid_until=_now() + timedelta(days=10),
        grace_days=15,
        features={'max_cameras': '12'},
    )
    svc = _service(monkeypatch)
    svc.initialize()

    assert svc.status() == 'valid'
    assert svc.is_usable() is True
    assert svc.features() == {'max_cameras': 12}
    assert svc.max_cameras() == 12
    assert svc.days_left() == 10

    db = SessionLocal()
    try:
        license_state_repo.update(db, status='expired', valid_until=_now() - timedelta(days=1))
        db.commit()
    finally:
        db.close()

    assert svc.status() == 'valid'  # snapshot cũ vẫn cache
    svc.refresh_snapshot()
    assert svc.status() == 'expired'
    assert svc.is_usable() is False
    assert svc.days_left() == 0


def test_set_enforcement_mode_persists_and_validates(monkeypatch):
    svc = _service(monkeypatch)
    svc.initialize()

    svc.set_enforcement_mode('enforce')
    assert svc.enforcement_mode() == 'enforce'
    row = _row()
    assert row is not None and row.enforcement_mode == 'enforce'

    svc.set_enforcement_mode('off')
    assert svc.enforcement_mode() == 'off'
    row = _row()
    assert row is not None and row.enforcement_mode == 'off'

    with pytest.raises(ValueError):
        svc.set_enforcement_mode('block')


def test_should_block_new_behavior(monkeypatch):
    svc = _service(monkeypatch)
    svc.initialize()
    svc.set_enforcement_mode('enforce')

    assert svc.should_block_new_behavior() is True  # unlicensed + enforce

    db = SessionLocal()
    try:
        license_state_repo.update(
            db,
            status='active',
            valid_until=_now() + timedelta(days=1),
            license_key_enc=encrypt_secret(TEST_LICENSE_KEY),
        )
        db.commit()
    finally:
        db.close()
    svc.refresh_snapshot()
    assert svc.should_block_new_behavior() is False

    svc.set_enforcement_mode('warn')
    assert svc.should_block_new_behavior() is False


def test_license_key_hint_masks_stored_key(monkeypatch):
    _seed_row(
        MACHINE_CODE,
        status='active',
        valid_until=_now() + timedelta(days=30),
        license_key_enc=encrypt_secret('KEYGATE-ABCD-1234'),
    )
    svc = _service(monkeypatch)
    svc.initialize()

    assert svc.license_key_hint() == '****1234'


def test_license_key_hint_is_none_when_unlicensed(monkeypatch):
    svc = _service(monkeypatch)
    svc.initialize()

    assert svc.license_key_hint() is None


# --- offline token TTL -----------------------------------------------------


def test_offline_token_expiry_degrades_lifetime_license(monkeypatch):
    """Lifetime (valid_until=None) không được miễn trừ token TTL."""
    expired = _now() - timedelta(hours=1)
    _seed_row(
        MACHINE_CODE,
        status='active',
        valid_until=None,
        token_exp=expired,
        last_verified_at=expired - timedelta(days=1),
    )
    svc = _service(monkeypatch)
    svc.initialize()

    snap = svc.snapshot()
    assert snap.valid_until is None
    assert snap.effective_status == 'expired'
    assert svc.status() == 'expired'
    assert svc.is_usable() is False
    assert snap.last_error == 'offline token expired; check-in required'


def test_offline_token_expiry_degrades_future_valid_until(monkeypatch):
    expired = _now() - timedelta(hours=1)
    _seed_row(
        MACHINE_CODE,
        status='active',
        valid_until=_now() + timedelta(days=365),
        token_exp=expired,
        last_verified_at=expired - timedelta(days=1),
    )
    svc = _service(monkeypatch)
    svc.initialize()

    assert svc.status() == 'expired'
    assert svc.is_usable() is False
    assert svc.snapshot().last_error == 'offline token expired; check-in required'


def test_fresh_offline_token_keeps_license_usable(monkeypatch):
    _seed_row(
        MACHINE_CODE,
        status='active',
        valid_until=None,
        token_exp=_now() + timedelta(days=7),
        last_verified_at=_now(),
    )
    svc = _service(monkeypatch)
    svc.initialize()

    assert svc.status() == 'valid'
    assert svc.is_usable() is True


def test_offline_token_expiry_ignored_after_fresher_verify(monkeypatch):
    """Verify thành công sau mốc token hết hạn = không còn dựa vào token cũ."""
    token_exp = _now() - timedelta(hours=2)
    _seed_row(
        MACHINE_CODE,
        status='active',
        valid_until=_now() + timedelta(days=30),
        token_exp=token_exp,
        last_verified_at=token_exp + timedelta(hours=1),
    )
    svc = _service(monkeypatch)
    svc.initialize()

    assert svc.status() == 'valid'
    assert svc.is_usable() is True
