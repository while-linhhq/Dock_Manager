"""URL xem ảnh/video media phải mở được từ trình duyệt ở xa.

Lỗi gốc: `/api/v1/detections/{id}/media` trả URL ký sẵn của MinIO
(`http://127.0.0.1:9100/...`) — trình duyệt chạy trên máy khác không tới được
127.0.0.1 của máy chủ, nên ảnh đối chiếu không hiển thị. Đường đúng là URL trên
chính origin API mà trình duyệt đã gọi (`/api/v1/media/preview/{token}`), token
là JWT ký sẵn có thời hạn, không cần header Authorization nên `<img>` dùng được.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.utils.media_token import (
    build_media_view_url,
    create_media_preview_token,
    decode_media_preview_token,
)

MINIO_URI = 's3://media/detections/29-09-2026/1452/images/fused_overlay_out.jpg'

def _request(scheme: str = 'https', host: str = 'api-basondock.iotforce.vn'):
    """Đối tượng tối thiểu giống starlette.Request cho phần base_url/method."""
    return SimpleNamespace(base_url=f'{scheme}://{host}/', method='GET', headers={})

def test_build_media_view_url_uses_public_base_from_settings(monkeypatch) -> None:
    from app.utils import media_token

    monkeypatch.setattr(
        media_token.settings, 'PUBLIC_BASE_URL', 'https://api.example.com', raising=False
    )
    url = build_media_view_url(MINIO_URI)

    assert url is not None
    assert url.startswith('https://api.example.com/api/v1/media/preview/')
    # Token phải giải ngược đúng đường dẫn MinIO gốc.
    token = url.rsplit('/', 1)[-1]
    assert decode_media_preview_token(token) == MINIO_URI


def test_build_media_view_url_falls_back_to_request_base(monkeypatch) -> None:
    from app.utils import media_token

    monkeypatch.setattr(media_token.settings, 'PUBLIC_BASE_URL', '', raising=False)
    monkeypatch.setattr(media_token.settings, 'ZALO_PUBLIC_BASE_URL', '', raising=False)

    url = build_media_view_url(MINIO_URI, request=_request('http', '127.0.0.1:8000'))

    assert url is not None
    assert url.startswith('http://127.0.0.1:8000/api/v1/media/preview/')


def test_build_media_view_url_prefers_settings_over_request(monkeypatch) -> None:
    """Qua Vite proxy, Host bị đổi thành 127.0.0.1:8000 — cấu hình phải thắng."""
    from app.utils import media_token

    monkeypatch.setattr(
        media_token.settings, 'PUBLIC_BASE_URL', 'https://api.example.com', raising=False
    )
    url = build_media_view_url(MINIO_URI, request=_request('http', '127.0.0.1:8000'))

    assert url is not None and url.startswith('https://api.example.com/')


def test_build_media_view_url_adds_mp4_suffix_for_video(monkeypatch) -> None:
    from app.utils import media_token

    monkeypatch.setattr(
        media_token.settings, 'PUBLIC_BASE_URL', 'https://api.example.com', raising=False
    )
    url = build_media_view_url('s3://media/detections/x/1452/videos/clip.mp4')

    assert url is not None and url.endswith('.mp4')
    # Token vẫn giải được dù có hậu tố .mp4.
    assert decode_media_preview_token(url.rsplit('/', 1)[-1]) == 's3://media/detections/x/1452/videos/clip.mp4'


def test_build_media_view_url_returns_none_without_base_or_path(monkeypatch) -> None:
    from app.utils import media_token

    monkeypatch.setattr(media_token.settings, 'PUBLIC_BASE_URL', '', raising=False)
    monkeypatch.setattr(media_token.settings, 'ZALO_PUBLIC_BASE_URL', '', raising=False)

    assert build_media_view_url(MINIO_URI) is None
    assert build_media_view_url('') is None


def test_media_view_url_serves_bytes_without_auth_header(monkeypatch) -> None:
    """URL trả về phải phục vụ được nội dung mà không cần Authorization."""
    from app.services import media_preview_service

    token = create_media_preview_token(MINIO_URI, ttl_hours=1)
    captured: dict = {}

    def fake_stream(minio_path, *, request=None, head_only=False):
        captured['path'] = minio_path
        from fastapi.responses import Response

        return Response(content=b'jpeg-bytes', media_type='image/jpeg')

    monkeypatch.setattr(media_preview_service, 'stream_minio_media', fake_stream)

    response = media_preview_service.serve_preview_media(token, _request())

    assert response.status_code == 200
    assert captured['path'] == MINIO_URI


def test_get_detection_media_rewrites_minio_paths_to_api_urls(monkeypatch) -> None:
    from app.api.v1.endpoints import detections as detections_module
    from app.utils import media_token

    monkeypatch.setattr(
        media_token.settings, 'PUBLIC_BASE_URL', 'https://api.example.com', raising=False
    )
    rows = [
        SimpleNamespace(id=5140, file_path=MINIO_URI),
        SimpleNamespace(id=5141, file_path='runs/local/only.jpg'),
    ]
    monkeypatch.setattr(
        detections_module.detection_media_repo,
        'get_by_detection',
        lambda db, detection_id: rows,
    )

    result = detections_module.get_detection_media(1452, _request(), db=None, _=None)

    assert result[0].file_path.startswith('https://api.example.com/api/v1/media/preview/')
    assert '127.0.0.1:9100' not in result[0].file_path
    # Đường dẫn không phải MinIO thì giữ nguyên.
    assert result[1].file_path == 'runs/local/only.jpg'


def test_detection_read_rewrites_audit_image_and_video(monkeypatch) -> None:
    from app.api.v1.endpoints import detections as detections_module
    from app.utils import media_token

    monkeypatch.setattr(
        media_token.settings, 'PUBLIC_BASE_URL', 'https://api.example.com', raising=False
    )
    obj = SimpleNamespace(
        audit_image_path='s3://media/detections/29-09-2026/1452/images/audit.jpg',
        video_path='s3://media/detections/29-09-2026/1452/videos/clip.mp4',
        unrelated='keep-me',
    )

    detections_module._with_media_view_paths(obj, _request())

    assert obj.audit_image_path.startswith('https://api.example.com/api/v1/media/preview/')
    assert obj.video_path.endswith('.mp4')
    assert obj.unrelated == 'keep-me'


def test_media_view_url_keeps_path_when_presign_would_break(monkeypatch) -> None:
    """Không có base nào (cấu hình rỗng, không có request) → giữ nguyên chuỗi gốc."""
    from app.api.v1.endpoints import detections as detections_module
    from app.utils import media_token

    monkeypatch.setattr(media_token.settings, 'PUBLIC_BASE_URL', '', raising=False)
    monkeypatch.setattr(media_token.settings, 'ZALO_PUBLIC_BASE_URL', '', raising=False)
    rows = [SimpleNamespace(id=1, file_path=MINIO_URI)]
    monkeypatch.setattr(
        detections_module.detection_media_repo,
        'get_by_detection',
        lambda db, detection_id: rows,
    )

    result = detections_module.get_detection_media(1452, None, db=None, _=None)

    assert result[0].file_path == MINIO_URI


def test_decode_media_preview_token_accepts_video_suffix() -> None:
    token = create_media_preview_token(MINIO_URI, ttl_hours=1)
    assert decode_media_preview_token(f'{token}.mp4') == MINIO_URI


def test_vessel_preview_uses_media_view_url(monkeypatch) -> None:
    """Ảnh tàu cũng phải là URL API, không phải presign MinIO 127.0.0.1."""
    from app.api.v1.endpoints import vessels as vessels_module
    from app.utils import media_token

    monkeypatch.setattr(
        media_token.settings, 'PUBLIC_BASE_URL', 'https://api.example.com', raising=False
    )

    def fail_presign(*args, **kwargs):  # pragma: no cover - chỉ chạy nếu còn gọi presign
        raise AssertionError('không được dùng presign MinIO cho ảnh hiển thị trên trình duyệt')

    monkeypatch.setattr(vessels_module, 'presign_get', fail_presign, raising=False)

    url = vessels_module._resolve_preview_url(
        vessel_id=7,
        point_id='p1',
        ship_id='ship-1',
        preview_uri='s3://media/visual_refs/ship-1/p1.jpg',
    )

    assert url is not None
    assert url.startswith('https://api.example.com/api/v1/media/preview/')
