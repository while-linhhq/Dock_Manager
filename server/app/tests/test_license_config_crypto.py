"""Unit tests for Keygate license settings + license-key encryption helper."""
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
