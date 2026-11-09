"""Test license/module dependencies + pipeline start gate (Task 10).

Không chạm mạng Keygate và không start pipeline thật: trạng thái license được
monkeypatch, ``camera_group_repo.get``/``pipeline_service.start_group`` được
thay bằng stub. Audit middleware cũng được stub để không ghi ``audit_logs``
vào PostgreSQL dùng chung.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.license import enforcement
from app.core.license import service as service_module
from app.main import app
from app.services.pipeline_service import PipelineService

client = TestClient(app)

LICENSE_BLOCKED_DETAIL = (
    'License không hợp lệ hoặc đã hết hạn. Không thể bắt đầu pipeline mới; '
    'pipeline đang chạy vẫn tiếp tục.'
)


@pytest.fixture(autouse=True)
def _stub_audit_writes(monkeypatch):
    """POST /pipeline/start đi qua audit middleware; không ghi audit_logs thật."""
    from app import main as main_module

    monkeypatch.setattr(
        main_module.audit_log_repo, 'create', lambda *args, **kwargs: None
    )


def _set_blocked(monkeypatch, blocked: bool) -> None:
    monkeypatch.setattr(
        service_module.license_service,
        'should_block_new_behavior',
        lambda: blocked,
    )


def _set_running(monkeypatch, running: bool) -> None:
    """Property ``is_running`` đọc process thật -> thay descriptor ở class."""
    monkeypatch.setattr(
        PipelineService, 'is_running', property(lambda self: running)
    )


def _set_group(monkeypatch, group) -> None:
    from app.api.v1.endpoints import pipeline as pipeline_endpoint

    monkeypatch.setattr(
        pipeline_endpoint.camera_group_repo,
        'get',
        lambda db, group_id: group,
    )


def _record_start(monkeypatch) -> list:
    from app.api.v1.endpoints import pipeline as pipeline_endpoint

    calls: list = []

    def _start_group(group, enable_ocr=True):
        calls.append((group, enable_ocr))

    monkeypatch.setattr(
        pipeline_endpoint.pipeline_service, 'start_group', _start_group
    )
    return calls


def _fake_group() -> SimpleNamespace:
    return SimpleNamespace(id=7, name='gate-test-group', is_active=True)


def test_enforce_pipeline_start_blocks_with_exact_detail(monkeypatch):
    _set_blocked(monkeypatch, True)

    with pytest.raises(HTTPException) as ei:
        enforcement.enforce_pipeline_start()

    assert ei.value.status_code == 403
    assert ei.value.detail == LICENSE_BLOCKED_DETAIL


def test_enforce_pipeline_start_allows_when_usable(monkeypatch):
    _set_blocked(monkeypatch, False)

    assert enforcement.enforce_pipeline_start() is None  # không raise


def test_require_license_state_blocks_with_exact_detail(monkeypatch):
    from app.api.deps import require_license_state

    _set_blocked(monkeypatch, True)

    with pytest.raises(HTTPException) as ei:
        require_license_state()

    assert ei.value.status_code == 403
    assert ei.value.detail == LICENSE_BLOCKED_DETAIL


def test_require_license_state_allows_when_usable(monkeypatch):
    from app.api.deps import require_license_state

    _set_blocked(monkeypatch, False)

    assert require_license_state() is None  # không raise


def test_require_license_state_has_no_auth_dependency():
    """Dependency thuần: /pipeline/start không auth (dev autostart)."""
    import inspect

    from app.api.deps import require_license_state

    assert list(inspect.signature(require_license_state).parameters) == []


def test_require_module_blocks_missing_feature(monkeypatch):
    from app.api.deps import require_module

    monkeypatch.setattr(service_module.license_service, 'features', lambda: {})
    dep = require_module('module_ai_lab')

    with pytest.raises(HTTPException) as ei:
        dep()

    assert ei.value.status_code == 403
    assert ei.value.detail == 'Module module_ai_lab chưa được cấp trong license'


def test_require_module_blocks_non_boolean_false(monkeypatch):
    from app.api.deps import require_module

    monkeypatch.setattr(
        service_module.license_service,
        'features',
        lambda: {'module_ai_lab': 'false'},
    )
    dep = require_module('module_ai_lab')

    with pytest.raises(HTTPException) as ei:
        dep()

    assert ei.value.status_code == 403


def test_require_module_allows_granted_feature(monkeypatch):
    from app.api.deps import require_module

    monkeypatch.setattr(
        service_module.license_service,
        'features',
        lambda: {'module_ai_lab': True},
    )
    dep = require_module('module_ai_lab')

    assert dep() is None  # không raise


def test_start_pipeline_returns_403_when_license_blocked(monkeypatch):
    _set_running(monkeypatch, False)
    _set_group(monkeypatch, _fake_group())
    calls = _record_start(monkeypatch)
    _set_blocked(monkeypatch, True)

    r = client.post('/api/v1/pipeline/start', json={'camera_group_id': 7})

    assert r.status_code == 403
    assert r.json()['detail'] == LICENSE_BLOCKED_DETAIL
    assert calls == []


def test_start_pipeline_keeps_running_pipeline_when_license_blocked(monkeypatch):
    """Early-return ``is_running`` đứng trước gate: pipeline đang chạy không bị đụng."""
    _set_running(monkeypatch, True)
    _set_group(monkeypatch, _fake_group())
    calls = _record_start(monkeypatch)
    _set_blocked(monkeypatch, True)

    r = client.post('/api/v1/pipeline/start', json={'camera_group_id': 7})

    assert r.status_code == 200
    assert r.json()['message'] == 'Pipeline is already running'
    assert calls == []


def test_start_pipeline_starts_group_when_license_usable(monkeypatch):
    _set_running(monkeypatch, False)
    group = _fake_group()
    _set_group(monkeypatch, group)
    calls = _record_start(monkeypatch)
    _set_blocked(monkeypatch, False)

    r = client.post('/api/v1/pipeline/start', json={'camera_group_id': 7})

    assert r.status_code == 200
    assert r.json()['message'] == 'Pipeline started'
    assert calls == [(group, True)]
