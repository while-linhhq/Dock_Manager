"""Unit tests for offline Ed25519 license-token verification (Keygate token)."""
import base64, json, time
from datetime import datetime, timezone
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from app.core.license.token import LicenseTokenError, verify_license_token

def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b'=').decode()

def _sign(payload: dict, key: Ed25519PrivateKey) -> str:
    p = _b64(json.dumps(payload).encode())
    return f'{p}.{_b64(key.sign(p.encode()))}'

def _keypair():
    priv = Ed25519PrivateKey.generate()
    pub_hex = priv.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
    return priv, pub_hex

def _claims(**over):
    base = {'lid': 'l1', 'pid': 'p1', 'pln': 'Standard', 'sts': 'active', 'did': 'inst-1',
            'ftr': {'max_cameras': '12'}, 'iat': int(time.time()), 'exp': int(time.time()) + 3600,
            'grc': 15, 'nce': 'n1', 'fpr': 'f' * 16}
    base.update(over)
    return base

def test_valid_token():
    priv, pub = _keypair()
    claims = verify_license_token(_sign(_claims(), priv), pub, expected_identifier='inst-1')
    assert claims.ftr == {'max_cameras': '12'}
    assert claims.grc == 15

def test_tampered_payload_fails():
    priv, pub = _keypair()
    token = _sign(_claims(), priv)
    payload, sig = token.split('.')
    with pytest.raises(LicenseTokenError):
        verify_license_token(f'{payload[:-2]}AA.{sig}', pub, expected_identifier='inst-1')

def test_wrong_identifier_fails():
    priv, pub = _keypair()
    with pytest.raises(LicenseTokenError):
        verify_license_token(_sign(_claims(), priv), pub, expected_identifier='other')

def test_expired_token_fails():
    priv, pub = _keypair()
    with pytest.raises(LicenseTokenError):
        verify_license_token(_sign(_claims(exp=int(time.time()) - 1), priv), pub, expected_identifier='inst-1')
