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


def test_error_constructors_accept_positional_args():
    err = KeygateError(404, 'LICENSE_NOT_FOUND')
    assert err.status == 404
    assert err.code == 'LICENSE_NOT_FOUND'
    assert err.details is None

    err = KeygateError(403, 'LICENSE_SUSPENDED', {'reason': 'x'}, 'suspended')
    assert (err.status, err.code, err.details, str(err)) == (
        403,
        'LICENSE_SUSPENDED',
        {'reason': 'x'},
        'suspended',
    )

    # Keyword construction keeps working.
    err = KeygateError(status=500, code='INTERNAL', details={'attempt': 1}, message='boom')
    assert (err.status, err.code, err.details, str(err)) == (500, 'INTERNAL', {'attempt': 1}, 'boom')

    net = KeygateNetworkError('down')
    assert isinstance(net, KeygateError)
    assert net.status is None and net.code is None and net.details is None
    assert str(net) == 'down'
