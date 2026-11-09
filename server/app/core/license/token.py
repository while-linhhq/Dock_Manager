"""Xác thực offline token license do Keygate phát hành (chữ ký Ed25519).

Token có dạng ``base64url(payload) + '.' + base64url(signature)``; chữ ký
Ed25519 được ký trên chính **chuỗi base64url(payload)** (không phải bytes JSON
đã giải mã) nên client verify hoàn toàn offline bằng public key lấy từ Keygate.

Mọi lỗi (sai định dạng, sai chữ ký, sai mã máy, hết hạn) đều được gói thành
:class:`LicenseTokenError` với lý do ngắn gọn, không chứa dữ liệu bí mật.
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

# Claim chuỗi bắt buộc: thiếu hoặc sai kiểu coi như token hỏng (fail closed).
# ``iat``/``exp``/``grc`` là int bắt buộc, ``vun``/``upd`` là int tuỳ chọn.
_REQUIRED_STR = ('lid', 'pid', 'pln', 'sts', 'did', 'nce', 'fpr')


class LicenseTokenError(Exception):
    """Token license không hợp lệ: định dạng, chữ ký, mã máy hoặc hạn dùng."""


@dataclass(frozen=True)
class LicenseTokenClaims:
    """Claim đã verify của token license; ``vun``/``upd`` có thể không có (None)."""

    lid: str
    pid: str
    pln: str
    sts: str
    did: str
    ftr: dict[str, Any]
    iat: int
    exp: int
    vun: int | None
    upd: int | None
    grc: int
    nce: str
    fpr: str


def _decode_b64url(value: str) -> bytes:
    """Giải mã base64url, khôi phục padding '=' bị lược bỏ khi phát hành token."""
    padding = '=' * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(value + padding)
    except ValueError as exc:
        raise LicenseTokenError('token có base64url không hợp lệ') from exc


def _required_int(raw: dict[str, Any], key: str) -> int:
    """Đọc claim int bắt buộc; ``bool`` kế thừa ``int`` nên cũng bị loại."""
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise LicenseTokenError(f'claim {key} thiếu hoặc không phải số nguyên')
    return value


def _optional_int(raw: dict[str, Any], key: str) -> int | None:
    """Đọc claim int tuỳ chọn; thiếu/None trả ``None``, sai kiểu là token hỏng."""
    value = raw.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise LicenseTokenError(f'claim {key} không phải số nguyên')
    return value


def _parse_payload(payload: bytes) -> dict[str, Any]:
    """``json.loads`` payload; payload không phải JSON object là token hỏng."""
    try:
        raw = json.loads(payload)
    except ValueError as exc:
        raise LicenseTokenError('payload không phải JSON hợp lệ') from exc
    if not isinstance(raw, dict):
        raise LicenseTokenError('payload không phải JSON object')
    return raw


def _build_claims(raw: dict[str, Any]) -> LicenseTokenClaims:
    """Validate đủ/sai kiểu các claim bắt buộc rồi dựng :class:`LicenseTokenClaims`."""
    for key in _REQUIRED_STR:
        if not isinstance(raw.get(key), str):
            raise LicenseTokenError(f'claim {key} thiếu hoặc không phải chuỗi')
    features = raw.get('ftr')
    if not isinstance(features, dict):
        raise LicenseTokenError('claim ftr thiếu hoặc không phải JSON object')
    return LicenseTokenClaims(
        lid=raw['lid'],
        pid=raw['pid'],
        pln=raw['pln'],
        sts=raw['sts'],
        did=raw['did'],
        ftr=dict(features),
        iat=_required_int(raw, 'iat'),
        exp=_required_int(raw, 'exp'),
        vun=_optional_int(raw, 'vun'),
        upd=_optional_int(raw, 'upd'),
        grc=_required_int(raw, 'grc'),
        nce=raw['nce'],
        fpr=raw['fpr'],
    )


def verify_license_token(
    token: str,
    public_key_hex: str,
    *,
    expected_identifier: str,
    now: datetime | None = None,
) -> LicenseTokenClaims:
    """Verify token license offline bằng public key Ed25519 (hex) của Keygate.

    - ``token``: ``base64url(payload) + '.' + base64url(signature)``.
    - ``public_key_hex``: public key thô 32 byte dạng hex (Keygate ``GET /license/pubkey``).
    - ``expected_identifier``: mã máy hiện tại; token phải có ``did`` trùng khớp.
    - ``now``: mốc thời gian để kiểm tra hạn dùng (mặc định UTC hiện tại);
      token hợp lệ khi ``now < exp``.

    Raises:
        LicenseTokenError: token sai định dạng/chữ ký, cấp cho máy khác, hoặc đã hết hạn.
    """
    if not isinstance(token, str) or not isinstance(public_key_hex, str):
        raise LicenseTokenError('token hoặc public key không phải chuỗi')
    parts = token.rsplit('.', 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise LicenseTokenError('token không đúng định dạng base64url(payload).base64url(signature)')
    payload_b64, signature_b64 = parts

    signature = _decode_b64url(signature_b64)
    payload = _decode_b64url(payload_b64)
    try:
        public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
    except (TypeError, ValueError) as exc:
        raise LicenseTokenError('public key Ed25519 không hợp lệ') from exc
    try:
        # Chữ ký phủ chính chuỗi base64url(payload), không phải bytes JSON.
        public_key.verify(signature, payload_b64.encode('ascii'))
    except InvalidSignature as exc:
        raise LicenseTokenError('chữ ký token không hợp lệ') from exc

    claims = _build_claims(_parse_payload(payload))
    if claims.did != expected_identifier:
        raise LicenseTokenError('token cấp cho máy khác (did không khớp)')
    now_ts = int((now if now is not None else datetime.now(timezone.utc)).timestamp())
    if now_ts >= claims.exp:
        raise LicenseTokenError('token đã hết hạn')
    return claims
