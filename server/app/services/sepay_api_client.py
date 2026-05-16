import logging
from datetime import datetime, timedelta
from typing import Any, Optional

import requests

logger = logging.getLogger('app.sepay.api')

SEPAY_API_BASE = 'https://my.sepay.vn'
SEPAY_LIST_PATH = '/userapi/transactions/list'
SEPAY_BANK_ACCOUNTS_PATH = '/userapi/bankaccounts/list'
SEPAY_REQUEST_TIMEOUT_SEC = 20


class SepayApiError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def list_transactions(
    api_token: str,
    *,
    account_number: str,
    since_id: Optional[int] = None,
    limit: int = 100,
    transaction_date_min: Optional[str] = None,
    transaction_date_max: Optional[str] = None,
) -> list[dict[str, Any]]:
    token = (api_token or '').strip()
    if not token:
        raise SepayApiError('SEPay API token is not configured')

    account = (account_number or '').strip()
    if not account:
        raise SepayApiError('SEPay bank account is not configured')

    params: dict[str, Any] = {
        'account_number': account,
        'limit': min(max(limit, 1), 500),
    }
    if since_id is not None and since_id > 0:
        params['since_id'] = since_id
    if transaction_date_min:
        params['transaction_date_min'] = transaction_date_min
    if transaction_date_max:
        params['transaction_date_max'] = transaction_date_max

    url = f'{SEPAY_API_BASE}{SEPAY_LIST_PATH}'
    headers = {'Authorization': f'Bearer {token}'}

    try:
        response = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=SEPAY_REQUEST_TIMEOUT_SEC,
        )
    except requests.RequestException as exc:
        raise SepayApiError(f'SEPay API request failed: {exc}') from exc

    if response.status_code == 429:
        retry_after = response.headers.get('x-sepay-userapi-retry-after', '2')
        raise SepayApiError(f'SEPay rate limit — retry after {retry_after}s', 429)

    if response.status_code >= 400:
        raise SepayApiError(
            f'SEPay API HTTP {response.status_code}: {response.text[:200]}',
            response.status_code,
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise SepayApiError('SEPay API returned invalid JSON') from exc

    status = payload.get('status')
    if status not in (200, '200'):
        err = payload.get('error') or payload.get('messages')
        raise SepayApiError(f'SEPay API error: {err}')

    transactions = payload.get('transactions')
    if not isinstance(transactions, list):
        return []
    return transactions


def list_bank_accounts(api_token: str, *, limit: int = 20) -> list[dict[str, Any]]:
    token = (api_token or '').strip()
    if not token:
        raise SepayApiError('SEPay API token is not configured')

    url = f'{SEPAY_API_BASE}{SEPAY_BANK_ACCOUNTS_PATH}'
    headers = {'Authorization': f'Bearer {token}'}

    try:
        response = requests.get(
            url,
            params={'limit': min(max(limit, 1), 100)},
            headers=headers,
            timeout=SEPAY_REQUEST_TIMEOUT_SEC,
        )
    except requests.RequestException as exc:
        raise SepayApiError(f'SEPay API request failed: {exc}') from exc

    if response.status_code >= 400:
        raise SepayApiError(
            f'SEPay bank accounts HTTP {response.status_code}: {response.text[:200]}',
            response.status_code,
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise SepayApiError('SEPay API returned invalid JSON') from exc

    status = payload.get('status')
    if status not in (200, '200'):
        err = payload.get('error') or payload.get('messages')
        raise SepayApiError(f'SEPay API error: {err}')

    accounts = payload.get('bankaccounts')
    if not isinstance(accounts, list):
        return []
    return accounts


def default_transaction_date_min(days: int = 30) -> str:
    start = datetime.now() - timedelta(days=days)
    return start.strftime('%Y-%m-%d %H:%M:%S')
