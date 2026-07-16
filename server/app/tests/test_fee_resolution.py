"""Unit tests for resolve_billable_fees — nguồn phí theo phân loại tàu.

Pure logic: stub vessel + monkeypatch fee_config_repo, không cần DB/GPU.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services import fee_resolution_service as frs


class _Repo:
    """Ghi lại lời gọi để assert đúng nhánh được chọn."""

    def __init__(self):
        self.by_vessel_calls = []
        self.by_type_calls = []

    def get_by_vessel(self, db, vessel_id, *, active_only=True):
        self.by_vessel_calls.append((vessel_id, active_only))
        return [f'spot_fee_v{vessel_id}']

    def get_by_vessel_type(self, db, vessel_type_id, *, active_only=True):
        self.by_type_calls.append((vessel_type_id, active_only))
        return [f'monthly_fee_t{vessel_type_id}']


@pytest.fixture
def repo(monkeypatch):
    r = _Repo()
    # resolve_billable_fees lazy-imports these inside the function body → patch at source.
    monkeypatch.setattr('app.repositories.fee_config_repository.fee_config_repo', r)
    return r


def _vessel(classification, vessel_id=10, vessel_type_id=None):
    return SimpleNamespace(
        id=vessel_id, classification=classification, vessel_type_id=vessel_type_id
    )


def test_spot_uses_per_vessel(repo):
    v = _vessel('spot', vessel_id=42)
    out = frs.resolve_billable_fees(db=None, vessel_or_id=v)
    assert out == ['spot_fee_v42']
    assert repo.by_vessel_calls == [(42, True)]
    assert repo.by_type_calls == []


def test_monthly_uses_per_type(repo):
    v = _vessel('monthly', vessel_id=7, vessel_type_id=344)
    out = frs.resolve_billable_fees(db=None, vessel_or_id=v)
    assert out == ['monthly_fee_t344']
    assert repo.by_type_calls == [(344, True)]
    assert repo.by_vessel_calls == []


def test_monthly_without_type_returns_empty(repo):
    v = _vessel('monthly', vessel_type_id=None)
    out = frs.resolve_billable_fees(db=None, vessel_or_id=v)
    assert out == []
    assert repo.by_vessel_calls == []
    assert repo.by_type_calls == []


def test_unclassified_returns_empty(repo):
    v = _vessel('unclassified', vessel_type_id=344)  # có type cũng KHÔNG tính
    out = frs.resolve_billable_fees(db=None, vessel_or_id=v)
    assert out == []
    assert repo.by_vessel_calls == []
    assert repo.by_type_calls == []


def test_none_classification_defaults_unclassified(repo):
    v = SimpleNamespace(id=1, classification=None, vessel_type_id=344)
    assert frs.resolve_billable_fees(db=None, vessel_or_id=v) == []


def test_none_vessel_returns_empty(repo):
    assert frs.resolve_billable_fees(db=None, vessel_or_id=None) == []


def test_active_only_false_propagates(repo):
    v = _vessel('spot', vessel_id=5)
    frs.resolve_billable_fees(db=None, vessel_or_id=v, active_only=False)
    assert repo.by_vessel_calls == [(5, False)]


def test_int_id_loads_vessel(monkeypatch, repo):
    v = _vessel('monthly', vessel_id=9, vessel_type_id=380)
    monkeypatch.setattr(
        'app.repositories.vessel_repository.vessel_repo',
        SimpleNamespace(get=lambda db, vid: v if vid == 9 else None),
    )
    out = frs.resolve_billable_fees(db=None, vessel_or_id=9)
    assert out == ['monthly_fee_t380']
    assert repo.by_type_calls == [(380, True)]


def test_int_id_missing_vessel_returns_empty(monkeypatch, repo):
    monkeypatch.setattr(
        'app.repositories.vessel_repository.vessel_repo',
        SimpleNamespace(get=lambda db, vid: None),
    )
    assert frs.resolve_billable_fees(db=None, vessel_or_id=999) == []
