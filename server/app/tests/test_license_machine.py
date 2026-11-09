"""Unit tests cho "mã máy" (hardware fingerprint) — không đọc host thật, không network."""
from __future__ import annotations

import logging

import pytest

from app.core.license.machine import (
    MACHINE_CODE_PREFIX,
    compute_machine_code,
    read_host_identity,
    resolve_machine_code,
)


def test_machine_code_is_deterministic_and_formatted():
    a = compute_machine_code({'machine_id': 'abc', 'product_uuid': 'def'})
    b = compute_machine_code({'product_uuid': 'def', 'machine_id': 'abc'})
    assert a == b and a.startswith('DSIGHT-') and len(a.split('-')) == 5


def test_machine_code_changes_with_hardware():
    assert compute_machine_code({'machine_id': 'abc'}) != compute_machine_code({'machine_id': 'xyz'})


def test_read_host_identity_never_raises():
    assert isinstance(read_host_identity(), dict)


def test_dev_override(monkeypatch):
    from app.core.license import machine
    monkeypatch.setattr(machine.settings, 'LICENSE_INSTANCE_ID', 'DEV-CODE', raising=False)
    assert resolve_machine_code() == 'DEV-CODE'


def test_machine_code_has_prefix_and_four_groups_of_four():
    code = compute_machine_code({'machine_id': 'abc'})
    parts = code.split('-')
    assert parts[0] == MACHINE_CODE_PREFIX
    assert [len(part) for part in parts[1:]] == [4, 4, 4, 4]
    assert code == code.upper()


def test_empty_sources_raise_value_error():
    with pytest.raises(ValueError):
        compute_machine_code({})


def test_blank_pairs_are_ignored():
    expected = compute_machine_code({'machine_id': 'abc'})
    assert compute_machine_code({'machine_id': 'abc', 'product_uuid': '   '}) == expected
    with pytest.raises(ValueError):
        compute_machine_code({'machine_id': '', 'product_uuid': '  '})


def test_read_host_identity_reads_files_and_skips_missing(tmp_path, monkeypatch):
    from app.core.license import machine

    machine_id = tmp_path / 'machine-id'
    machine_id.write_text('  mid-123  \n', encoding='utf-8')
    board_serial = tmp_path / 'board_serial'
    board_serial.write_text('BOARD-42\n', encoding='utf-8')

    monkeypatch.setattr(
        machine,
        'HOST_IDENTITY_PATHS',
        {
            'machine_id': machine_id,
            'product_uuid': tmp_path / 'missing-product-uuid',
            'board_serial': board_serial,
        },
    )
    assert machine.read_host_identity() == {
        'machine_id': 'mid-123',
        'board_serial': 'BOARD-42',
    }


def test_read_host_identity_skips_unreadable_entries(tmp_path, monkeypatch):
    from app.core.license import machine

    a_directory = tmp_path / 'not-a-file'
    a_directory.mkdir()
    monkeypatch.setattr(machine, 'HOST_IDENTITY_PATHS', {'machine_id': a_directory})
    assert machine.read_host_identity() == {}


def test_resolve_without_host_identity_returns_empty_and_warns(monkeypatch, caplog):
    from app.core.license import machine

    monkeypatch.setattr(machine.settings, 'LICENSE_INSTANCE_ID', '', raising=False)
    monkeypatch.setattr(machine, 'read_host_identity', lambda: {})
    with caplog.at_level(logging.WARNING):
        assert resolve_machine_code() == ''
    assert 'host identity' in caplog.text.lower()


def test_resolve_computes_from_host_identity(monkeypatch):
    from app.core.license import machine

    monkeypatch.setattr(machine.settings, 'LICENSE_INSTANCE_ID', '', raising=False)
    monkeypatch.setattr(machine, 'read_host_identity', lambda: {'machine_id': 'abc'})
    assert resolve_machine_code() == compute_machine_code({'machine_id': 'abc'})
