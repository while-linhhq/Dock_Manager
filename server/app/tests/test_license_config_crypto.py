"""Unit tests for Keygate license settings + license-key encryption helper."""
import logging
from pathlib import Path
from types import SimpleNamespace

from app.core import startup_report
from app.core.config import settings
from app.utils.crypto import decrypt_secret, encrypt_secret

def test_license_settings_defaults():
    assert settings.LICENSE_SERVER_URL == 'https://license.dtgsoft.vn'
    assert settings.LICENSE_ENFORCEMENT == 'warn'
    assert settings.LICENSE_CHECKIN_HOURS == 6

def test_secret_roundtrip():
    token = encrypt_secret('DSIGHT-ABCD-1234')
    assert token != 'DSIGHT-ABCD-1234'
    assert decrypt_secret(token) == 'DSIGHT-ABCD-1234'

def test_decrypt_invalid_returns_none():
    assert decrypt_secret('not-a-fernet-token') is None


def test_startup_warns_loudly_for_default_or_empty_secret_key(monkeypatch, caplog):
    for secret in ('', 'secret'):
        monkeypatch.setattr(
            startup_report, 'settings', SimpleNamespace(SECRET_KEY=secret)
        )
        with caplog.at_level(logging.WARNING):
            assert startup_report.warn_if_insecure_secret_key() is True

    assert 'SECRET_KEY' in caplog.text
    assert 'KHÔNG được bảo vệ' in caplog.text


def test_startup_does_not_warn_for_strong_secret_key(monkeypatch, caplog):
    monkeypatch.setattr(
        startup_report, 'settings', SimpleNamespace(SECRET_KEY='a' * 64)
    )

    with caplog.at_level(logging.WARNING):
        assert startup_report.warn_if_insecure_secret_key() is False
    assert 'SECRET_KEY' not in caplog.text


def test_env_example_requires_strong_secret_key_placeholder():
    env_example = (Path(__file__).resolve().parents[2] / '.env.example').read_text(
        encoding='utf-8'
    )

    assert 'SECRET_KEY=<generate with: python -c' in env_example
    assert 'secrets.token_hex(32)' in env_example
