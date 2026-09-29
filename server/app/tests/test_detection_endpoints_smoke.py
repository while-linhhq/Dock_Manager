"""Smoke test cấp route cho các endpoint detections.

Bài học từ lỗi thật: thêm `request=request` vào chỗ gọi `_detection_to_read` nhưng quên
khai báo `request: Request` trong chữ ký endpoint → FastAPI trả 500 ở `/detections/`
mà test đơn vị (gọi hàm trực tiếp) không phát hiện. Test này đi qua đúng tầng FastAPI.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.db.session import get_db
from app.main import app


@pytest.fixture()
def client(monkeypatch):
    from app.api.v1.endpoints import detections as detections_module

    now = datetime(2026, 9, 29, 7, 42, 3, tzinfo=timezone.utc)
    row = SimpleNamespace(
        id=1452,
        vessel_id=None,
        track_id='gid_test',
        start_time=now,
        end_time=now,
        video_path='s3://media/detections/29-09-2026/1452/videos/clip.mp4',
        audit_image_path='s3://media/detections/29-09-2026/1452/images/audit.jpg',
        ocr_results=[],
        confidence=0.9,
        is_accepted=None,
        verified_by=None,
        verified_at=None,
        rejection_reason=None,
        created_at=now,
        berth_in_time=now,
        berth_out_time=now,
        deleted_at=None,
        berth_out_source=None,
        berth_in_source=None,
    )
    media_row = SimpleNamespace(
        id=5140,
        detection_id=1452,
        media_type='image',
        file_path='s3://media/detections/29-09-2026/1452/images/fused.jpg',
        file_size=123,
        created_at=now,
    )

    # Trả bản sao mỗi lần gọi: production nạp row mới từ DB, không tái dùng object đã bị sửa.
    def _fresh(obj):
        return SimpleNamespace(**vars(obj))

    monkeypatch.setattr(detections_module.detection_repo, 'get_all', lambda db, **kw: [_fresh(row)])
    # `get_db` ở đây trả None nên count_filtered thật sẽ nổ khi gọi db.query;
    # stub để smoke test vẫn đo được tầng route (200 + shape response).
    monkeypatch.setattr(detections_module.detection_repo, 'count_filtered', lambda db, **kw: 1)
    monkeypatch.setattr(detections_module.detection_repo, 'get', lambda db, _id: _fresh(row))
    monkeypatch.setattr(
        detections_module.detection_media_repo,
        'get_by_detection',
        lambda db, _id: [_fresh(media_row)],
    )
    monkeypatch.setattr(detections_module, 'resolve_camera_in_out', lambda db, ids: {})
    monkeypatch.setattr(
        detections_module, 'compute_detection_over_berth_limit', lambda db, obj: False
    )

    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1, is_active=True)
    test_client = TestClient(app)  # không dùng context manager: bỏ qua lifespan (không bật pipeline/GPU)
    yield test_client
    test_client.close()
    app.dependency_overrides.clear()


def test_list_detections_returns_200(client) -> None:
    response = client.get('/api/v1/detections/?limit=2')

    assert response.status_code == 200, response.text[:300]


def test_get_detection_returns_200(client) -> None:
    response = client.get('/api/v1/detections/1452')

    assert response.status_code == 200, response.text[:300]


def test_get_detection_media_returns_api_urls(client, monkeypatch) -> None:
    from app.utils import media_token

    monkeypatch.setattr(
        media_token.settings, 'PUBLIC_BASE_URL', 'https://api.example.com', raising=False
    )

    response = client.get('/api/v1/detections/1452/media')

    assert response.status_code == 200, response.text[:300]
    url = response.json()[0]['file_path']
    assert url.startswith('https://api.example.com/api/v1/media/preview/')
    assert '127.0.0.1' not in url


def test_list_detections_media_paths_are_browser_reachable(client, monkeypatch) -> None:
    """Có cờ include_presigned_paths → URL media qua API; không có cờ → giữ nguyên s3://."""
    from app.utils import media_token

    monkeypatch.setattr(
        media_token.settings, 'PUBLIC_BASE_URL', 'https://api.example.com', raising=False
    )

    response = client.get('/api/v1/detections/?limit=2&include_presigned_paths=true')

    assert response.status_code == 200, response.text[:300]
    audit = response.json()[0].get('audit_image_path') or ''
    assert audit.startswith('https://api.example.com/api/v1/media/preview/')
    assert '127.0.0.1' not in audit

    raw = client.get('/api/v1/detections/?limit=2')
    assert raw.status_code == 200, raw.text[:300]
    assert (raw.json()[0].get('audit_image_path') or '').startswith('s3://')
