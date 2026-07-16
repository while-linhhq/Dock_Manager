from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.services import registry_expiry_alert_service as alert_service
from app.services import zalo_service


def test_collects_all_three_berthing_alerts(monkeypatch):
    start = datetime(2026, 7, 13, 10, 0, tzinfo=timezone.utc)  # Monday 17:00 VN
    end = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)  # Monday 19:00 VN
    detection = SimpleNamespace(
        id=101,
        start_time=start.replace(tzinfo=None),
        end_time=end.replace(tzinfo=None),
        berth_in_time=start,
        berth_out_time=end,
    )
    vessel = SimpleNamespace(
        id=7,
        ship_id='SG-TEST',
        name='Test vessel',
        registry_expiry=date(2026, 7, 12),
    )
    fee = SimpleNamespace(
        operating_hours={'mon': {'open': '06:00', 'close': '18:00'}},
        max_berth_duration_minutes=60,
    )
    monkeypatch.setattr(alert_service, '_resolve_alert_fees', lambda db, value: [fee])

    alerts = alert_service._collect_alerts(
        object(),
        detection,
        vessel,
        today=date(2026, 7, 14),
    )

    assert {alert.kind for alert in alerts} == {
        alert_service.REGISTRY_EXPIRED_KIND,
        alert_service.OUTSIDE_HOURS_KIND,
        alert_service.OVER_DURATION_KIND,
    }
    assert all('SG-TEST' in alert.caption for alert in alerts)
    assert any('1 giờ' in alert.caption for alert in alerts)
    assert any('2 giờ' in alert.caption for alert in alerts)


def test_alert_sender_uses_dedicated_bot_token(monkeypatch):
    calls = []
    monkeypatch.setattr(zalo_service.settings, 'ZALO_ALERT_BOT_TOKEN', 'alert-token')
    monkeypatch.setattr(
        zalo_service,
        '_call_zalo_api_with_token',
        lambda token, method, payload: calls.append((token, method, payload)) or {'ok': True},
    )

    zalo_service.send_alert_text_message('alert-chat', 'test warning')

    assert calls == [
        ('alert-token', 'sendMessage', {'chat_id': 'alert-chat', 'text': 'test warning'})
    ]
