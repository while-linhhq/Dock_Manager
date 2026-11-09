import pytest
import requests

from app.core.license.keygate_client import KeygateClient, KeygateError, KeygateNetworkError


class _Resp:
    def __init__(self, status, payload):
        self.status_code, self._payload = status, payload

    def json(self):
        return self._payload


def test_activate_unwraps_data(monkeypatch):
    calls = {}

    def fake_request(method, url, json=None, timeout=None, headers=None):
        calls.update(method=method, url=url, json=json)
        return _Resp(200, {'success': True, 'data': {'status': 'activated', 'token': 't'}})

    monkeypatch.setattr(requests, 'request', fake_request)
    out = KeygateClient('https://kg.test').activate('K', 'inst-1', 'port-a')
    assert out['status'] == 'activated'
    assert calls['url'] == 'https://kg.test/api/v1/license/activate'
    assert calls['json'] == {'license_key': 'K', 'identifier': 'inst-1', 'label': 'port-a'}


def test_404_maps_to_license_not_found(monkeypatch):
    monkeypatch.setattr(
        requests,
        'request',
        lambda *a, **k: _Resp(
            404,
            {'success': False, 'error': {'code': 'LICENSE_NOT_FOUND', 'message': 'x'}},
        ),
    )
    with pytest.raises(KeygateError) as ei:
        KeygateClient('https://kg.test').verify('K', 'inst-1')
    assert ei.value.status == 404 and ei.value.code == 'LICENSE_NOT_FOUND'


def test_network_error_wrapped(monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError('down')

    monkeypatch.setattr(requests, 'request', boom)
    with pytest.raises(KeygateNetworkError):
        KeygateClient('https://kg.test').verify('K', 'inst-1')
