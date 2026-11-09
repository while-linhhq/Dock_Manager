#!/usr/bin/env python3
"""Probe staging/dev cho license Keygate — công cụ vận hành, app không import.

Chạy từ thư mục ``server/`` (hoặc bất kỳ đâu, script tự thêm ``server/`` vào
``sys.path``)::

    cd server
    LICENSE_PROBE_URL=https://stg-license.dtgsoft.vn \
    LICENSE_PROBE_KEY=<key> \
    python scripts/license_probe.py

Env:
    ``LICENSE_PROBE_URL``         bắt buộc — base URL Keygate (không có ``/api``).
    ``LICENSE_PROBE_KEY``         bắt buộc — license key cần kiểm tra.
    ``LICENSE_PROBE_IDENTIFIER``  tuỳ chọn — identifier gửi Keygate; mặc định
                                 ``probe-<uuid4>`` (mỗi lần chạy là một "máy"
                                 mới nên chỉ dùng với license tạm/throwaway).
    ``LICENSE_HTTP_TIMEOUT_SEC``  tuỳ chọn — timeout HTTP (giây), mặc định 5.0.

Script gọi ``activate`` → ``verify`` → ``entitlements`` → ``public_key`` rồi
verify token offline bằng ``verify_license_token``. In status/plan/valid_until/
features; exit 0 khi mọi bước OK, 1 khi API/token lỗi, 2 khi thiếu cấu hình.
**Không bao giờ in license key** (mọi message lỗi đều được redact).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from uuid import uuid4

# Chạy trực tiếp ``python scripts/license_probe.py``: sys.path[0] là scripts/,
# phải thêm thư mục server/ để import được package ``app``.
_SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVER_ROOT))

from app.core.license.keygate_client import (  # noqa: E402
    KeygateClient,
    KeygateError,
    KeygateNetworkError,
)
from app.core.license.token import LicenseTokenError, verify_license_token  # noqa: E402

_DEFAULT_TIMEOUT_SEC = 5.0


def _timeout_sec() -> float:
    """Timeout HTTP từ ``LICENSE_HTTP_TIMEOUT_SEC`` (mặc định 5.0 giây)."""
    raw = os.environ.get('LICENSE_HTTP_TIMEOUT_SEC', '').strip()
    if not raw:
        return _DEFAULT_TIMEOUT_SEC
    try:
        value = float(raw)
    except ValueError:
        return _DEFAULT_TIMEOUT_SEC
    return value if value > 0 else _DEFAULT_TIMEOUT_SEC


def _redact(text: object, secret: str) -> str:
    """Xoá license key khỏi message trước khi in (không log key ở bất kỳ đâu)."""
    message = str(text)
    if secret:
        message = message.replace(secret, '***')
    return message


def _config_error(message: str) -> int:
    print(f'PROBE CONFIG ERROR: {message}', file=sys.stderr)
    return 2


def _probe_failed(message: str, secret: str) -> int:
    print(f'PROBE FAILED: {_redact(message, secret)}', file=sys.stderr)
    return 1


def main() -> int:
    url = os.environ.get('LICENSE_PROBE_URL', '').strip()
    license_key = os.environ.get('LICENSE_PROBE_KEY', '').strip()
    identifier = os.environ.get('LICENSE_PROBE_IDENTIFIER', '').strip()

    missing = [
        name
        for name, value in (
            ('LICENSE_PROBE_URL', url),
            ('LICENSE_PROBE_KEY', license_key),
        )
        if not value
    ]
    if missing:
        return _config_error(
            f'thiếu env {", ".join(missing)}; xem docstring đầu file để biết cách chạy'
        )
    if not url.startswith(('http://', 'https://')):
        return _config_error('LICENSE_PROBE_URL phải bắt đầu bằng http:// hoặc https://')

    if not identifier:
        identifier = f'probe-{uuid4().hex}'

    client = KeygateClient(url, timeout=_timeout_sec())
    print('License probe — không in license key')
    print(f'url: {url}')
    print(f'identifier: {identifier}')

    try:
        activated = client.activate(license_key, identifier, label='staging probe')
        verified = client.verify(license_key, identifier)
        entitlements = client.entitlements(license_key)
        public_key = client.public_key()
    except KeygateNetworkError as exc:
        return _probe_failed(f'không kết nối được Keygate: {exc}', license_key)
    except KeygateError as exc:
        code = exc.code or 'KEYGATE_ERROR'
        return _probe_failed(
            f'Keygate trả HTTP {exc.status} {code}: {exc}', license_key
        )
    except Exception as exc:  # response hỏng/JSON lạ — không in traceback
        return _probe_failed(f'lỗi không mong đợi: {type(exc).__name__}: {exc}', license_key)

    activated = activated if isinstance(activated, dict) else {}
    verified = verified if isinstance(verified, dict) else {}
    entitlements = entitlements if isinstance(entitlements, dict) else {}

    token = verified.get('token') or activated.get('token')
    if not isinstance(token, str) or not token.strip():
        return _probe_failed('response activate/verify không có token để verify', license_key)

    try:
        claims = verify_license_token(
            token.strip(),
            public_key,
            expected_identifier=identifier,
        )
    except LicenseTokenError as exc:
        return _probe_failed(f'token không verify được: {exc}', license_key)

    print(f'activate_status: {activated.get("status") or "-"}')
    print(f'status: {verified.get("status") or claims.sts or "-"}')
    print(f'plan: {verified.get("plan_name") or verified.get("plan_id") or claims.pln or "-"}')
    print(f'valid_until: {verified.get("valid_until") or "-"}')
    print(
        'features: '
        + json.dumps(
            verified.get('features') or claims.ftr or {},
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    print(
        'entitlements: '
        + json.dumps(entitlements, ensure_ascii=False, sort_keys=True)
    )
    print(f'token: OK (exp={claims.exp}, grace_days={claims.grc})')
    print('PROBE OK')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
