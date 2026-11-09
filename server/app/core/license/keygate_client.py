"""HTTP client mỏng cho Keygate license API (v0.1.20).

Keygate trả mọi response thành công dưới dạng ``{"success": true, "data": ...}``
và lỗi dưới dạng ``{"success": false, "error": {"code": ..., "details": ...}}``.
Client chỉ gọi đúng 4 endpoint SDK; **không retry** — ``LicenseService`` quyết
định retry/backoff và phân biệt lỗi mạng với lỗi nghiệp vụ.
"""
from __future__ import annotations

from typing import Any

import requests

_ACCEPT_JSON = {'Accept': 'application/json'}


class KeygateError(Exception):
    """Keygate trả về non-2xx (hoặc response lỗi) — lỗi nghiệp vụ có ngữ cảnh."""

    def __init__(
        self,
        status: int | None = None,
        code: str | None = None,
        details: dict[str, Any] | None = None,
        message: str = '',
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.details = details


class KeygateNetworkError(KeygateError):
    """Không kết nối được Keygate (timeout, DNS, mất mạng) — lỗi tạm thời."""

    def __init__(self, message: str = '') -> None:
        super().__init__(status=None, message=message)


class KeygateClient:
    """Gọi API license của Keygate; trả về ``data`` đã bóc vỏ."""

    def __init__(self, base_url: str, timeout: float = 5.0) -> None:
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout

    def activate(self, license_key: str, identifier: str, label: str = '') -> dict[str, Any]:
        """Kích hoạt license cho ``identifier`` (mã máy) và trả token + metadata."""
        return self._post(
            '/api/v1/license/activate',
            {'license_key': license_key, 'identifier': identifier, 'label': label},
        )

    def verify(self, license_key: str, identifier: str) -> dict[str, Any]:
        """Verify license của ``identifier``, trả token/metadata mới."""
        return self._post(
            '/api/v1/license/verify',
            {'license_key': license_key, 'identifier': identifier},
        )

    def entitlements(self, license_key: str) -> dict[str, Any]:
        """Lấy plan/addon entitlements hiện tại của license."""
        return self._post('/api/v1/license/entitlements', {'license_key': license_key})

    def public_key(self) -> str:
        """Public key Ed25519 (hex) dùng verify token offline."""
        data = self._get('/api/v1/license/pubkey')
        value = data.get('public_key')
        if not isinstance(value, str) or not value.strip():
            raise KeygateError(status=None, message='malformed response')
        return value.strip()

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request('POST', path, payload)

    def _get(self, path: str) -> dict[str, Any]:
        return self._request('GET', path, None)

    def _request(self, method: str, path: str, payload: dict[str, Any] | None) -> dict[str, Any]:
        try:
            response = requests.request(
                method,
                f'{self.base_url}{path}',
                json=payload,
                timeout=self.timeout,
                headers=_ACCEPT_JSON,
            )
        except requests.RequestException as exc:
            raise KeygateNetworkError(f'Không kết nối được Keygate: {exc}') from exc

        if not 200 <= response.status_code < 300:
            raise _error_from_response(response)

        try:
            body = response.json()
        except ValueError as exc:
            raise KeygateError(
                status=response.status_code,
                message='malformed response',
            ) from exc

        data = body.get('data') if isinstance(body, dict) else None
        if not isinstance(data, dict):
            raise KeygateError(
                status=response.status_code,
                message='malformed response',
            )
        return data


def _error_from_response(response: requests.Response) -> KeygateError:
    """Ánh xạ response non-2xx sang :class:`KeygateError` (body hỏng → code None)."""
    try:
        body = response.json()
    except ValueError:
        body = None

    error = body.get('error') if isinstance(body, dict) else None
    if not isinstance(error, dict):
        error = {}

    code = error.get('code')
    details = error.get('details')
    message = error.get('message') or f'Keygate trả về HTTP {response.status_code}'
    return KeygateError(
        response.status_code,
        code if isinstance(code, str) else None,
        details if isinstance(details, dict) else None,
        message,
    )
