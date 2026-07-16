from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.ai.boat_tracker import TrackedBoat, TrackState
from app.services.pipeline_service import PipelineService


def _track(ship_id: str | None, *, track_id: str = 'trk_1') -> TrackedBoat:
    return TrackedBoat(
        track_id=track_id,
        state=TrackState.CONFIRMED,
        box=MagicMock(),
        conf=0.9,
        hits=5,
        misses=0,
        first_seen_ts=100.0,
        last_seen_ts=110.0,
        ship_id=ship_id,
        camera_id=1,
        ever_confirmed=True,
    )


@pytest.fixture
def persist_harness(monkeypatch):
    svc = PipelineService()
    svc._media_collector = MagicMock()
    svc._media_collector.pop_any.return_value = None
    svc._video_registry = MagicMock()
    svc._video_registry.take_for_any_track_ids.return_value = None
    svc._lookup_track_ids = MagicMock(return_value=['trk_1'])
    svc._camera_has_boundary = MagicMock(return_value=True)

    vessel = SimpleNamespace(id=10, ship_id='SG-1234')
    det = SimpleNamespace(
        id=20,
        track_id='trk_1',
        video_path=None,
        audit_image_path=None,
    )

    monkeypatch.setattr(
        'app.services.pipeline_service.vessel_repo.get_by_ship_id_normalized',
        MagicMock(return_value=vessel),
    )
    monkeypatch.setattr(
        'app.services.pipeline_service.vessel_repo.update_last_seen',
        MagicMock(return_value=vessel),
    )
    create_mock = MagicMock(return_value=det)
    monkeypatch.setattr('app.services.pipeline_service.detection_repo.create', create_mock)
    monkeypatch.setattr('app.services.pipeline_service.order_repo.get_pending_by_vessel', MagicMock(return_value=None))
    monkeypatch.setattr('app.services.pipeline_service.port_log_repo.get_logs_by_date', MagicMock(return_value=[]))
    monkeypatch.setattr('app.services.pipeline_service.port_log_repo.create', MagicMock(return_value=None))
    monkeypatch.setattr('app.services.detection_invoice_service.ensure_ai_invoice_for_detection', MagicMock(return_value=None), raising=False)
    monkeypatch.setattr('app.services.registry_expiry_alert_service.schedule_berthing_alerts', MagicMock(return_value=None), raising=False)

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = det
    return svc, db, create_mock


def test_persist_known_ship_even_without_berth_in(persist_harness):
    """Regression: tàu đã nhận diện biển số vẫn phải lưu detection dù chưa chạm berth zone."""
    svc, db, create_mock = persist_harness

    svc._persist_track_removed(db, _track('SG-1234'), [('SG-1234', 0.95)])

    create_mock.assert_called_once()


def test_skip_unknown_ship_without_berth_in(persist_harness):
    """Unknown/no OCR ngoài berth zone vẫn bị bỏ qua để giảm false positive."""
    svc, db, create_mock = persist_harness

    svc._persist_track_removed(db, _track('UNKNOWN'), [])

    create_mock.assert_not_called()
