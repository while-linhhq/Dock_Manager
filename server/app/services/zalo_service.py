from __future__ import annotations

import logging
import re
import threading
from datetime import datetime, timezone
from typing import Any, Optional

import requests
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.zalo_notification import ZaloNotification
from app.repositories.detection_repository import detection_repo
from app.repositories.port_config_repository import port_config_repo
from app.repositories.vessel_repository import vessel_repo
from app.schemas.vessel import VesselCreate
from app.services.ship_id_utils import is_unknown_ship_id, normalize_ship_id
from app.utils.media_short_link import build_zalo_short_media_url

_log = logging.getLogger('app.services.zalo')

ZALO_API_BASE = 'https://bot-api.zaloplatforms.com/bot'
ZALO_CHAT_ID_CONFIG_KEY = 'zalo_chat_id'
ZALO_WEBHOOK_PATH = '/api/v1/zalo/webhook'
ZALO_WEBHOOK_ORIGIN_PATH = '/api/v1/zalo/webhook-origin'
# Zalo Bot fetches sendPhoto URLs with the same Java UA as webhooks — often blocked by Cloudflare.
_ZALO_MEDIA_FETCH_UA = 'Java/1.8.0_192'


def _resolve_webhook_base_url() -> str:
    """HTTPS base for Zalo setWebhook (no trailing slash)."""
    explicit = str(settings.ZALO_WEBHOOK_BASE_URL or '').strip().rstrip('/')
    if explicit:
        return explicit
    return str(settings.ZALO_PUBLIC_BASE_URL or '').strip().rstrip('/')


def build_webhook_url(*, use_origin_path: bool = False) -> str:
    base = _resolve_webhook_base_url()
    if not base:
        return ''
    path = ZALO_WEBHOOK_ORIGIN_PATH if use_origin_path else ZALO_WEBHOOK_PATH
    return f'{base}{path}'
_SET_COMMAND_RE = re.compile(r'^SET\s+(\d+)\s+(.+)$', re.IGNORECASE)
_SKIP_COMMAND_RE = re.compile(r'^(?:SKIP|BOQUA|BỎ\s*QUA|Bỏ\s*qua)\s+#?(\d+)$', re.IGNORECASE)
_GOIY_COMMAND_RE = re.compile(r'^(?:GOIY|GOI\s*Y|GỢI\s*Ý|HINT)\s+#?(\d+)$', re.IGNORECASE)
_ACTION_RE = re.compile(r'^act:(\d+):([msc])(?::(.+))?$', re.IGNORECASE)
ZALO_PENDING_CONFIG_PREFIX = 'zalo_pending_detection_'


def _zalo_enabled() -> bool:
    return bool(settings.ZALO_ENABLED and settings.ZALO_BOT_TOKEN)


def _resolve_chat_id(db: Session) -> str:
    env_chat = str(settings.ZALO_CHAT_ID or '').strip()
    if env_chat:
        return env_chat
    row = port_config_repo.get_by_key(db, ZALO_CHAT_ID_CONFIG_KEY)
    return str(row.value or '').strip() if row else ''


def _save_chat_id(db: Session, chat_id: str) -> None:
    value = str(chat_id or '').strip()
    if not value:
        return
    port_config_repo.upsert(
        db,
        key=ZALO_CHAT_ID_CONFIG_KEY,
        value=value,
        description='Zalo Bot chat ID for unknown-ship notifications',
    )


def _call_zalo_api(method: str, payload: dict[str, Any]) -> dict[str, Any]:
    token = str(settings.ZALO_BOT_TOKEN or '').strip()
    if not token:
        raise ValueError('ZALO_BOT_TOKEN is not configured')
    url = f'{ZALO_API_BASE}{token}/{method}'
    response = requests.post(url, json=payload, timeout=30)
    response.raise_for_status()
    data = response.json()
    if not data.get('ok', False):
        raise RuntimeError(f'Zalo API {method} failed: {data}')
    return data


def _call_zalo_api_allow_timeout(method: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Like _call_zalo_api but treats getUpdates long-poll timeout as empty result."""
    token = str(settings.ZALO_BOT_TOKEN or '').strip()
    if not token:
        raise ValueError('ZALO_BOT_TOKEN is not configured')
    url = f'{ZALO_API_BASE}{token}/{method}'
    response = requests.post(url, json=payload, timeout=max(35, int(payload.get('timeout', 5)) + 10))
    response.raise_for_status()
    data = response.json()
    if data.get('ok', False):
        return data
    if method == 'getUpdates' and data.get('error_code') == 408:
        return {'ok': True, 'result': []}
    raise RuntimeError(f'Zalo API {method} failed: {data}')


def _format_detection_time(start_time: Optional[datetime]) -> str:
    if start_time is None:
        return '-'
    dt = start_time
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone()
    return local.strftime('%H:%M %d/%m/%Y')


def _zalo_can_fetch_url(url: str) -> bool:
    """Probe URL the way Zalo Bot Platform downloads sendPhoto assets."""
    target = str(url or '').strip()
    if not target.lower().startswith('https://'):
        return False
    headers = {'User-Agent': _ZALO_MEDIA_FETCH_UA}
    try:
        resp = requests.head(target, timeout=12, allow_redirects=True, headers=headers)
        if resp.status_code in (200, 206):
            return True
        if resp.status_code == 404:
            # Route exists but object missing — still not OK for sendPhoto.
            return False
        if resp.status_code == 405:
            with requests.get(target, timeout=20, stream=True, headers=headers) as get_resp:
                return get_resp.status_code in (200, 206)
    except Exception as exc:
        _log.debug('Zalo media URL probe failed url=%s: %s', target, exc)
    return False


def _minio_object_ready(minio_path: Optional[str]) -> bool:
    from app.services.storage.s3_service import get_object_size

    path = str(minio_path or '').strip()
    if not path.startswith('minio://') and not path.startswith('s3://'):
        return False
    return get_object_size(path) is not None


def _build_media_url(minio_path: Optional[str], *, video: bool = False) -> Optional[str]:
    path = str(minio_path or '').strip()
    if not path or not _minio_object_ready(path):
        return None
    # Zalo rejects long JWT preview URLs (424). Always use short links on webhook/media/v/.
    url = build_zalo_short_media_url(path, cache_bust=True)
    if url:
        return url
    _log.error('Failed to build Zalo short media URL for %s', path)
    return None


def _build_unified_caption(
    *,
    detection_id: int,
    camera_name: str,
    start_time: Optional[datetime],
    video_url: Optional[str],
) -> str:
    det = int(detection_id)
    lines = [
        '🚢 XÁC NHẬN DANH TÍNH TÀU',
        f'📋 Mã phát hiện: #{det}',
        f'🕐 Thời gian: {_format_detection_time(start_time)}',
        f'📷 Camera đơn: {camera_name or "-"}',
        '⚠️ Trạng thái: CHƯA XÁC ĐỊNH',
    ]
    if video_url:
        lines.extend(['', '🎬 Video ghi hình:', video_url])
    lines.extend(
        [
            '',
            '👉 Gõ lệnh để xử lý:',
            f'SET {det} [MÃ TÀU] — xác nhận',
            f'SKIP {det} — bỏ qua',
            f'GOIY {det} — gợi ý mã tàu',
        ]
    )
    return '\n'.join(lines)[:2000]


def _pending_config_key(chat_id: str) -> str:
    return f'{ZALO_PENDING_CONFIG_PREFIX}{chat_id}'


def _get_pending_detection_id(db: Session, chat_id: str) -> Optional[int]:
    row = port_config_repo.get_by_key(db, _pending_config_key(chat_id))
    if not row:
        return None
    raw = str(row.value or '').strip()
    return int(raw) if raw.isdigit() else None


def _set_pending_detection_id(db: Session, chat_id: str, detection_id: Optional[int]) -> None:
    key = _pending_config_key(chat_id)
    if detection_id is None:
        port_config_repo.delete_by_key(db, key)
        return
    port_config_repo.upsert(
        db,
        key=key,
        value=str(int(detection_id)),
        description='Zalo chat awaiting manual ship ID for detection',
    )


def _extract_message_id(result: Any) -> Optional[str]:
    if not isinstance(result, dict):
        return None
    mid = result.get('message_id')
    return str(mid).strip() if mid else None


def _notification_exists(db: Session, detection_id: int) -> bool:
    return (
        db.query(ZaloNotification)
        .filter(ZaloNotification.detection_id == detection_id)
        .first()
        is not None
    )


def _create_notification_row(
    db: Session,
    detection_id: int,
    chat_id: str,
    *,
    status: str = 'pending_media',
) -> bool:
    row = ZaloNotification(
        detection_id=detection_id,
        chat_id=chat_id,
        status=status,
    )
    db.add(row)
    try:
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False


def _resolve_media_paths(
    db: Session,
    detection_id: int,
    *,
    image_hint: Optional[str] = None,
    video_hint: Optional[str] = None,
) -> tuple[Optional[str], Optional[str]]:
    image_path, video_path = resolve_notification_media(db, detection_id)
    if not image_path and image_hint:
        image_path = str(image_hint).strip() or None
    if not video_path and video_hint:
        video_path = str(video_hint).strip() or None
    return image_path, video_path


def _media_bundle_is_ready(
    db: Session,
    detection_id: int,
    *,
    image_hint: Optional[str] = None,
    video_hint: Optional[str] = None,
    require_video: bool,
) -> tuple[Optional[str], Optional[str], bool]:
    image_path, video_path = _resolve_media_paths(
        db,
        detection_id,
        image_hint=image_hint,
        video_hint=video_hint,
    )
    image_ready = bool(image_path and _minio_object_ready(image_path))
    if not image_ready:
        return image_path, video_path, False
    if require_video:
        video_ready = bool(video_path and _minio_object_ready(video_path))
        return image_path, video_path, video_ready
    return image_path, video_path, True


def _wait_for_media_bundle(
    detection_id: int,
    *,
    image_hint: Optional[str] = None,
    video_hint: Optional[str] = None,
    require_video: bool,
    max_wait_sec: int | None = None,
    poll_sec: float | None = None,
) -> tuple[Optional[str], Optional[str], bool]:
    """Poll DB + MinIO until image (and video if required) are ready."""
    import time

    deadline = time.monotonic() + max(
        5,
        int(max_wait_sec if max_wait_sec is not None else settings.ZALO_NOTIFY_MEDIA_WAIT_SEC),
    )
    interval = max(1.0, float(poll_sec if poll_sec is not None else settings.ZALO_NOTIFY_MEDIA_POLL_SEC))

    while time.monotonic() < deadline:
        db = SessionLocal()
        try:
            image_path, video_path, ready = _media_bundle_is_ready(
                db,
                detection_id,
                image_hint=image_hint,
                video_hint=video_hint,
                require_video=require_video,
            )
            if ready:
                return image_path, video_path, True
        finally:
            db.close()
        time.sleep(interval)

    db = SessionLocal()
    try:
        image_path, video_path, ready = _media_bundle_is_ready(
            db,
            detection_id,
            image_hint=image_hint,
            video_hint=video_hint,
            require_video=False,
        )
        return image_path, video_path, ready
    finally:
        db.close()


def _deliver_unknown_detection(
    *,
    detection_id: int,
    image_path: Optional[str],
    video_path: Optional[str],
    camera_name: str = '',
    start_time: Optional[datetime] = None,
    force_resend: bool = False,
) -> None:
    """Build URLs and send Zalo photo/message after media is confirmed ready."""
    if not _zalo_enabled():
        return

    db = SessionLocal()
    try:
        existing = (
            db.query(ZaloNotification)
            .filter(ZaloNotification.detection_id == detection_id)
            .first()
        )
        if existing and not force_resend:
            if existing.status in ('sent', 'awaiting_ship_id'):
                _log.info('Skip Zalo notify detection_id=%s: already notified', detection_id)
                return
        if existing and force_resend:
            db.delete(existing)
            db.commit()

        chat_id = _resolve_chat_id(db)
        if not chat_id:
            _log.warning(
                'Skip Zalo notify detection_id=%s: ZALO_CHAT_ID not configured',
                detection_id,
            )
            return

        if not existing or force_resend:
            if not _create_notification_row(db, detection_id, chat_id, status='pending_media'):
                _log.info('Skip Zalo notify detection_id=%s: duplicate notification row', detection_id)
                return

        det = detection_repo.get(db, detection_id)
        if not image_path or not video_path:
            resolved_image, resolved_video = _resolve_media_paths(db, detection_id)
            image_path = image_path or resolved_image
            video_path = video_path or resolved_video
        if det is not None and start_time is None:
            start_time = getattr(det, 'start_time', None)

        if not image_path or not _minio_object_ready(image_path):
            notif = (
                db.query(ZaloNotification)
                .filter(ZaloNotification.detection_id == detection_id)
                .first()
            )
            if notif is not None:
                notif.status = 'failed'
                db.commit()
            _log.warning(
                'Zalo notify detection_id=%s aborted: image not ready path=%s',
                detection_id,
                image_path,
            )
            return

        image_url = _build_media_url(image_path)
        video_url = _build_media_url(video_path, video=True) if video_path else None
        caption = _build_unified_caption(
            detection_id=detection_id,
            camera_name=camera_name,
            start_time=start_time,
            video_url=video_url,
        )

        notif = (
            db.query(ZaloNotification)
            .filter(ZaloNotification.detection_id == detection_id)
            .first()
        )

        try:
            sent = False
            if image_url:
                for attempt in range(3):
                    if attempt > 0:
                        import time

                        time.sleep(1.5)
                        image_url = _build_media_url(image_path)
                        if not image_url:
                            break
                    if not image_url:
                        continue
                    try:
                        data = _call_zalo_api(
                            'sendPhoto',
                            {
                                'chat_id': chat_id,
                                'photo': image_url,
                                'caption': caption,
                            },
                        )
                        result = data.get('result') or {}
                        if notif is not None:
                            message_id = _extract_message_id(result)
                            notif.photo_message_id = message_id
                            notif.header_message_id = message_id
                            notif.video_message_id = message_id
                        sent = True
                        break
                    except RuntimeError as exc:
                        if '424' not in str(exc):
                            raise
                        _log.warning(
                            'Zalo sendPhoto rejected url=%s detection_id=%s attempt=%s: %s',
                            image_url,
                            detection_id,
                            attempt + 1,
                            exc,
                        )

            if not sent:
                text = caption
                if image_url:
                    text = f'{caption}\n\n📷 Ảnh: {image_url}'
                elif image_path:
                    _log.warning(
                        'Zalo notify detection_id=%s: sendPhoto failed, falling back to text (minio=%s)',
                        detection_id,
                        image_path,
                    )
                data = _call_zalo_api(
                    'sendMessage',
                    {
                        'chat_id': chat_id,
                        'text': text[:2000],
                    },
                )
                result = data.get('result') or {}
                if notif is not None:
                    message_id = _extract_message_id(result)
                    notif.header_message_id = message_id

            if notif is not None:
                notif.status = 'sent'
                db.commit()

            _log.info(
                'Zalo notification sent detection_id=%s chat_id=%s mode=%s image=%s video=%s',
                detection_id,
                chat_id,
                'sendPhoto' if sent else 'sendMessage',
                bool(image_path),
                bool(video_path),
            )
        except Exception:
            _log.exception('Zalo notify failed detection_id=%s', detection_id)
            if notif is not None:
                notif.status = 'failed'
                db.commit()
    finally:
        db.close()


def notify_unknown_detection(
    *,
    detection_id: int,
    image_minio_path: Optional[str] = None,
    video_minio_path: Optional[str] = None,
    camera_name: str = '',
    start_time: Optional[datetime] = None,
    force_resend: bool = False,
    expect_video: bool | None = None,
    wait_for_media: bool = True,
) -> None:
    """Wait for media bundle then send Zalo confirmation (blocking)."""
    if not _zalo_enabled():
        return

    require_video = (
        bool(expect_video)
        if expect_video is not None
        else bool(str(video_minio_path or '').strip())
    )

    image_path: Optional[str] = None
    video_path: Optional[str] = None
    if wait_for_media:
        _log.info(
            'Zalo notify detection_id=%s: waiting for media (require_video=%s, max=%ss)',
            detection_id,
            require_video,
            settings.ZALO_NOTIFY_MEDIA_WAIT_SEC,
        )
        image_path, video_path, ready = _wait_for_media_bundle(
            detection_id,
            image_hint=image_minio_path,
            video_hint=video_minio_path,
            require_video=require_video,
        )
        if not ready:
            _log.warning(
                'Zalo notify detection_id=%s: media wait timeout (image=%s video=%s require_video=%s)',
                detection_id,
                image_path,
                video_path,
                require_video,
            )
    else:
        db = SessionLocal()
        try:
            image_path, video_path = _resolve_media_paths(
                db,
                detection_id,
                image_hint=image_minio_path,
                video_hint=video_minio_path,
            )
        finally:
            db.close()

    _deliver_unknown_detection(
        detection_id=detection_id,
        image_path=image_path,
        video_path=video_path,
        camera_name=camera_name,
        start_time=start_time,
        force_resend=force_resend,
    )


def _deferred_notify_worker(**kwargs) -> None:
    detection_id = int(kwargs.get('detection_id') or 0)
    try:
        notify_unknown_detection(**kwargs)
    except Exception:
        _log.exception('Zalo deferred notify failed detection_id=%s', detection_id)


def schedule_unknown_detection_notify(**kwargs) -> None:
    """Queue Zalo notify — waits until image (+ video if expected) exist on MinIO."""
    if not _zalo_enabled():
        return

    detection_id = int(kwargs.get('detection_id') or 0)
    if detection_id <= 0:
        return

    db = SessionLocal()
    try:
        chat_id = _resolve_chat_id(db)
        if not chat_id:
            _log.warning('Skip Zalo schedule detection_id=%s: ZALO_CHAT_ID not configured', detection_id)
            return

        existing = (
            db.query(ZaloNotification)
            .filter(ZaloNotification.detection_id == detection_id)
            .first()
        )
        if existing:
            if existing.status in ('sent', 'awaiting_ship_id', 'pending_media'):
                _log.info('Skip Zalo schedule detection_id=%s: already queued or sent', detection_id)
                return
            if existing.status == 'failed':
                existing.status = 'pending_media'
                db.commit()
            else:
                return
        elif not _create_notification_row(db, detection_id, chat_id, status='pending_media'):
            return
    finally:
        db.close()

    threading.Thread(
        target=_deferred_notify_worker,
        kwargs=kwargs,
        daemon=True,
        name=f'zalo-notify-{detection_id}',
    ).start()


def notify_unknown_detection_async(**kwargs) -> None:
    """Backward-compatible alias — schedules deferred notify."""
    schedule_unknown_detection_notify(**kwargs)


def _reassign_vessel_identity(db: Session, detection_id: int, new_ship_id: str) -> str:
    normalized = normalize_ship_id(new_ship_id)
    if not normalized or is_unknown_ship_id(normalized):
        raise ValueError('Ma tau khong hop le')

    det = detection_repo.get(db, detection_id)
    if not det:
        raise ValueError(f'Khong tim thay detection #{detection_id}')

    vessel = vessel_repo.get_by_ship_id_normalized(db, normalized)
    if not vessel:
        vessel = vessel_repo.create(db, VesselCreate(ship_id=normalized))
    else:
        vessel_repo.update_last_seen(db, vessel.id)

    detection_repo.update_vessel_id(db, detection_id, vessel.id)

    notif = (
        db.query(ZaloNotification)
        .filter(ZaloNotification.detection_id == detection_id)
        .first()
    )
    if notif is not None:
        notif.status = 'identified'
        notif.resolved_ship_id = normalized
        notif.resolved_at = datetime.now(timezone.utc)
        db.commit()

    try:
        from app.services.detection_invoice_service import ensure_ai_invoice_for_detection

        ensure_ai_invoice_for_detection(detection_id)
    except Exception:
        _log.exception('AI invoice after Zalo identity failed detection_id=%s', detection_id)

    return normalized


def _recent_ship_suggestions(db: Session, *, limit: int = 5) -> list[str]:
    from app.models.vessel import Vessel

    rows = (
        db.query(Vessel)
        .filter(Vessel.is_active.is_(True))
        .order_by(Vessel.last_seen.desc().nullslast(), Vessel.id.desc())
        .limit(max(limit * 3, limit))
        .all()
    )
    ids: list[str] = []
    for vessel in rows:
        ship_id = normalize_ship_id(str(getattr(vessel, 'ship_id', '') or ''))
        if ship_id and not is_unknown_ship_id(ship_id) and ship_id not in ids:
            ids.append(ship_id)
        if len(ids) >= limit:
            break
    return ids


def _format_hint_message(detection_id: int, suggestions: list[str]) -> str:
    lines = [f'🔎 Gợi ý mã tàu cho phát hiện #{detection_id}:']
    for ship_id in suggestions:
        lines.append(f'• SET {detection_id} {ship_id}')
    lines.append(f'Hoặc: SET {detection_id} [MÃ KHÁC]')
    return '\n'.join(lines)


def _handle_action(chat_id: str, detection_id: int, action: str, ship_id: str = '') -> str:
    db = SessionLocal()
    try:
        env_chat = str(settings.ZALO_CHAT_ID or '').strip()
        if env_chat and str(chat_id) != env_chat:
            return 'Bạn không có quyền xác nhận danh tính tàu.'

        if action == 's':
            from app.services.detection_cleanup_service import purge_detection_resources

            result = purge_detection_resources(db, detection_id)
            if not result.get('found'):
                return f'Không tìm thấy phát hiện #{detection_id}.'
            if _get_pending_detection_id(db, chat_id) == detection_id:
                _set_pending_detection_id(db, chat_id, None)
            return f'Đã bỏ qua và xóa phát hiện #{detection_id}.'

        if action == 'm':
            _set_pending_detection_id(db, chat_id, detection_id)
            notif = (
                db.query(ZaloNotification)
                .filter(ZaloNotification.detection_id == detection_id)
                .first()
            )
            if notif is not None:
                notif.status = 'awaiting_ship_id'
                db.commit()
            return (
                f'Nhập mã tàu cho phát hiện #{detection_id}:\n'
                f'• Gõ mã trực tiếp (vd: BA-12345)\n'
                f'• Hoặc: SET {detection_id} BA-12345'
            )

        if action == 'h':
            suggestions = _recent_ship_suggestions(db)
            if not suggestions:
                return f'Chưa có mã tàu gợi ý. Nhập: SET {detection_id} [MÃ TÀU]'
            return _format_hint_message(detection_id, suggestions)

        if action == 'c':
            resolved = _reassign_vessel_identity(db, detection_id, ship_id)
            if _get_pending_detection_id(db, chat_id) == detection_id:
                _set_pending_detection_id(db, chat_id, None)
            return f'✅ Đã xác nhận phát hiện #{detection_id}: {resolved}'

        return 'Thao tác không hợp lệ.'
    except ValueError as exc:
        return str(exc)
    except Exception:
        _log.exception('Zalo action failed detection_id=%s action=%s', detection_id, action)
        return 'Lỗi hệ thống. Vui lòng thử lại.'
    finally:
        db.close()


def _parse_incoming_text(text: str) -> Optional[tuple[str, int, str, str]]:
    """
    Returns tuple(action_kind, detection_id, action_code, ship_id)
    action_kind: 'set' | 'act' | 'pending_plain'
    """
    raw = (text or '').strip()
    if not raw:
        return None

    match = _SET_COMMAND_RE.match(raw)
    if match:
        return ('set', int(match.group(1)), 'c', match.group(2).strip())

    match = _SKIP_COMMAND_RE.match(raw)
    if match:
        return ('act', int(match.group(1)), 's', '')

    match = _GOIY_COMMAND_RE.match(raw)
    if match:
        return ('act', int(match.group(1)), 'h', '')

    match = _ACTION_RE.match(raw)
    if match:
        return ('act', int(match.group(1)), match.group(2).lower(), (match.group(3) or '').strip())

    return None


def handle_incoming_message(chat_id: str, text: str) -> Optional[str]:
    """Parse manager reply / menu action and reassign vessel identity."""
    parsed = _parse_incoming_text(text)
    if parsed:
        kind, detection_id, action, ship_id = parsed
        if kind == 'set':
            return _handle_action(chat_id, detection_id, 'c', ship_id)
        return _handle_action(chat_id, detection_id, action, ship_id)

    db = SessionLocal()
    try:
        pending_id = _get_pending_detection_id(db, chat_id)
        if pending_id is not None and text.strip():
            return _handle_action(chat_id, pending_id, 'c', text.strip())
    finally:
        db.close()

    return None


def _extract_postback_payload(body: dict[str, Any]) -> Optional[str]:
    message = body.get('message')
    if not isinstance(message, dict):
        return None
    for key in ('postback', 'callback_query', 'button'):
        block = message.get(key)
        if isinstance(block, dict):
            payload = str(block.get('payload') or block.get('data') or '').strip()
            if payload:
                return payload
    payload = str(message.get('payload') or message.get('callback_data') or '').strip()
    return payload or None


def process_incoming_payload(body: dict[str, Any]) -> None:
    """Handle one Zalo webhook / getUpdates payload."""
    _log.info('Zalo event received: %s', body)
    result = _normalize_event_result(body)
    if result is None:
        result = body.get('result') if isinstance(body.get('result'), dict) else None
    if not isinstance(result, dict):
        return

    event_name = str(result.get('event_name') or '')
    message = result.get('message')
    if not isinstance(message, dict):
        return

    chat = message.get('chat') if isinstance(message.get('chat'), dict) else {}
    chat_id = str(chat.get('id') or '').strip()
    if chat_id:
        remember_chat_from_webhook(chat_id)

    postback_payload = _extract_postback_payload(result)
    if postback_payload:
        reply = handle_incoming_message(chat_id, postback_payload)
        if reply:
            try:
                send_text_message(chat_id, reply)
            except Exception:
                _log.exception('Failed to send Zalo postback reply chat_id=%s', chat_id)
        return

    if event_name != 'message.text.received':
        return

    text = str(message.get('text') or '').strip()
    if not text or not chat_id:
        return

    reply = handle_incoming_message(chat_id, text)
    if reply:
        try:
            send_text_message(chat_id, reply)
        except Exception:
            _log.exception('Failed to send Zalo reply for chat_id=%s', chat_id)
    elif not _ACTION_RE.match(text) and not _SET_COMMAND_RE.match(text) and not _SKIP_COMMAND_RE.match(text) and not _GOIY_COMMAND_RE.match(text):
        try:
            send_text_message(
                chat_id,
                'Khi có tàu chưa xác định, bot gửi ảnh + hướng dẫn lệnh.\n'
                'SET [ID] [MÃ TÀU] — xác nhận\n'
                'SKIP [ID] — bỏ qua\n'
                'GOIY [ID] — gợi ý mã',
            )
        except Exception:
            _log.exception('Failed to send Zalo greeting for chat_id=%s', chat_id)


def _normalize_event_result(payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    if not isinstance(payload, dict):
        return None
    if 'event_name' in payload:
        return payload
    inner = payload.get('result')
    if isinstance(inner, dict) and 'event_name' in inner:
        return inner
    return None


def remember_chat_from_webhook(chat_id: str) -> None:
    """Persist chat.id from webhook or polling."""
    value = str(chat_id or '').strip()
    if not value:
        return
    db = SessionLocal()
    try:
        previous = _resolve_chat_id(db)
        _save_chat_id(db, value)
        if previous != value:
            _log.info('Updated Zalo chat_id: %s -> %s', previous or '(none)', value)
        elif not previous:
            _log.info('Saved Zalo chat_id from webhook: %s', value)
    finally:
        db.close()


def _clear_saved_chat_id() -> None:
    db = SessionLocal()
    try:
        port_config_repo.delete_by_key(db, ZALO_CHAT_ID_CONFIG_KEY)
        _log.info('Cleared invalid Zalo chat_id from port_configs')
    finally:
        db.close()


def send_text_message(
    chat_id: str,
    text: str,
    *,
    reply_markup: Optional[dict[str, Any]] = None,
) -> None:
    payload: dict[str, Any] = {'chat_id': chat_id, 'text': text}
    if reply_markup:
        payload['reply_markup'] = reply_markup
    try:
        _call_zalo_api('sendMessage', payload)
    except RuntimeError as exc:
        err = str(exc).lower()
        if 'chat_id is invaild' in err or 'error_code' in err and '410' in err:
            _clear_saved_chat_id()
        raise


def get_resolved_chat_id() -> str:
    db = SessionLocal()
    try:
        return _resolve_chat_id(db)
    finally:
        db.close()


def get_bot_info() -> dict[str, Any]:
    """Fetch bot profile from Zalo getMe."""
    if not _zalo_enabled():
        return {}
    data = _call_zalo_api('getMe', {})
    result = data.get('result') or {}
    if not isinstance(result, dict):
        return {}
    return {
        'bot_id': str(result.get('id') or ''),
        'display_name': str(result.get('display_name') or ''),
        'account_name': str(result.get('account_name') or ''),
        'account_type': str(result.get('account_type') or ''),
        'can_join_groups': bool(result.get('can_join_groups')),
    }


def _persist_bot_info_to_port_configs(db: Session) -> None:
    info = get_bot_info()
    bot_id = str(info.get('bot_id') or '').strip()
    if not bot_id:
        return
    port_config_repo.upsert(
        db,
        key='zalo_bot_id',
        value=bot_id,
        description='Zalo Bot ID (from getMe)',
    )
    display = str(info.get('display_name') or '').strip()
    if display:
        port_config_repo.upsert(
            db,
            key='zalo_bot_display_name',
            value=display,
            description='Zalo Bot display name',
        )


def sync_chat_id_from_updates(*, timeout_sec: int = 8) -> Optional[str]:
    """
    Temporarily remove webhook and poll getUpdates to discover manager chat_id.
    Restores webhook before returning.
    """
    if not _zalo_enabled():
        return None

    webhook_url = build_webhook_url()
    secret = str(settings.ZALO_WEBHOOK_SECRET or '').strip()

    try:
        _call_zalo_api('deleteWebhook', {})
        data = _call_zalo_api_allow_timeout('getUpdates', {'timeout': str(max(3, timeout_sec))})
    except Exception:
        _log.exception('Zalo getUpdates failed')
        data = {}
    finally:
        if (
            webhook_url
            and len(secret) >= 8
            and not settings.ZALO_POLLING_ENABLED
        ):
            try:
                _call_zalo_api('setWebhook', {'url': webhook_url, 'secret_token': secret})
            except Exception:
                _log.exception('Zalo setWebhook restore failed')

    updates = data.get('result') if isinstance(data, dict) else None
    events: list[dict[str, Any]] = []
    if isinstance(updates, list):
        for item in updates:
            if not isinstance(item, dict):
                continue
            normalized = _normalize_event_result(item)
            events.append(normalized if normalized else item)
    elif isinstance(updates, dict) and updates.get('event_name'):
        events = [updates]

    chat_id: Optional[str] = None
    for result in reversed(events):
        if not isinstance(result, dict):
            continue
        message = result.get('message')
        if not isinstance(message, dict):
            continue
        chat = message.get('chat') if isinstance(message.get('chat'), dict) else {}
        cid = str(chat.get('id') or '').strip()
        if cid:
            chat_id = cid
            break

    if chat_id:
        db = SessionLocal()
        try:
            _save_chat_id(db, chat_id)
        finally:
            db.close()
    return chat_id


def send_test_message(*, chat_id: Optional[str] = None, text: Optional[str] = None) -> dict[str, Any]:
    """Send a test message from bot to manager."""
    if not _zalo_enabled():
        raise ValueError('Zalo bot is not enabled or token is missing')

    db = SessionLocal()
    try:
        target = str(chat_id or '').strip() or _resolve_chat_id(db)
    finally:
        db.close()

    if not target:
        target = sync_chat_id_from_updates() or ''

    if not target:
        raise ValueError(
            'Chua co chat_id. Hay mo Zalo, nhan tin "xin chao" cho bot, roi goi lai endpoint test.'
        )

    message = (text or '').strip() or (
        'Xin chao! Day la tin nhan test tu he thong Dock Manager (Bason Bach Dang).'
    )
    data = _call_zalo_api('sendMessage', {'chat_id': target, 'text': message})
    return {
        'chat_id': target,
        'text': message,
        'zalo_response': data.get('result'),
    }


def check_media_java_ua_probe(*, sample_code: str = 'healthcheck') -> dict[str, Any]:
    """Probe whether Zalo's Java UA can fetch webhook/media URLs (sendPhoto prerequisite)."""
    public_base = str(settings.ZALO_PUBLIC_BASE_URL or '').strip().rstrip('/')
    if not public_base:
        return {'checked': False, 'reason': 'ZALO_PUBLIC_BASE_URL not set'}

    sample_url = f'{public_base}/api/v1/zalo/webhook/media/v/{sample_code}.jpg'
    legacy_url = f'{public_base}/api/v1/media/v/{sample_code}.jpg'
    headers = {'User-Agent': _ZALO_MEDIA_FETCH_UA}

    def _probe(url: str) -> dict[str, Any]:
        try:
            resp = requests.head(url, timeout=12, allow_redirects=True, headers=headers)
            blocked = resp.status_code == 403 and '1010' in (resp.text or '')
            return {
                'url': url,
                'status_code': resp.status_code,
                'java_ua_blocked': blocked,
                'reachable_by_zalo': resp.status_code in (200, 206, 404),
            }
        except Exception as exc:
            return {'url': url, 'error': str(exc), 'reachable_by_zalo': False}

    webhook_media = _probe(sample_url)
    legacy_media = _probe(legacy_url)
    return {
        'checked': True,
        'webhook_media': webhook_media,
        'legacy_media': legacy_media,
        'hint': (
            'Cloudflare chặn Java UA trên /api/v1/media/*. '
            'Cập nhật deploy/cloudflare/zalo-platform-worker.js và redeploy Worker '
            '(route api/v1/zalo/webhook* phải proxy GET /webhook/media/*).'
            if legacy_media.get('java_ua_blocked') or not webhook_media.get('reachable_by_zalo')
            else None
        ),
    }


def check_webhook_java_ua_probe() -> dict[str, Any]:
    """Optional probe: Zalo webhook requests use User-Agent Java/1.8.0_192."""
    webhook_base = _resolve_webhook_base_url()
    secret = str(settings.ZALO_WEBHOOK_SECRET or '').strip()
    if not webhook_base or not secret:
        return {'checked': False, 'reason': 'missing webhook base URL or webhook secret'}

    url = build_webhook_url()
    try:
        response = requests.post(
            url,
            json={'ok': True, 'result': {}},
            headers={
                'Content-Type': 'application/json',
                'X-Bot-Api-Secret-Token': secret,
                'User-Agent': 'Java/1.8.0_192',
            },
            timeout=15,
        )
        java_ua_blocked = response.status_code == 403 and '1010' in (response.text or '')
        return {
            'checked': True,
            'url': url,
            'status_code': response.status_code,
            'java_ua_blocked': java_ua_blocked,
            'hint': (
                'Cloudflare chan User-Agent Java/1.8.0_192 (loi 1010). '
                'Dat ZALO_POLLING_ENABLED=true (khong can cau hinh Cloudflare). '
                'Hoac nho admin zone iotforce.io.vn mo firewall cho path /api/v1/zalo/webhook.'
                if java_ua_blocked
                else None
            ),
            'recommended_fix': (
                'ZALO_POLLING_ENABLED=true'
                if java_ua_blocked
                else None
            ),
        }
    except Exception as exc:
        return {'checked': True, 'url': url, 'error': str(exc)}


def get_setup_info() -> dict[str, Any]:
    db = SessionLocal()
    try:
        _persist_bot_info_to_port_configs(db)
        chat_id = _resolve_chat_id(db)
        bot = get_bot_info()
        bot_id_row = port_config_repo.get_by_key(db, 'zalo_bot_id')
        public_base = str(settings.ZALO_PUBLIC_BASE_URL or '').strip().rstrip('/')
        webhook_base = _resolve_webhook_base_url()
        webhook_url = build_webhook_url() if webhook_base else None
        cf_check = check_webhook_java_ua_probe() if webhook_base else {'checked': False}
        media_check = check_media_java_ua_probe() if public_base else {'checked': False}
        webhook_info: dict[str, Any] = {}
        try:
            webhook_info = get_webhook_info()
        except Exception:
            pass
        return {
            'enabled': _zalo_enabled(),
            'mode': 'polling' if settings.ZALO_POLLING_ENABLED else 'webhook',
            'bot_id': bot.get('bot_id') or (bot_id_row.value if bot_id_row else None),
            'bot_display_name': bot.get('display_name') or None,
            'bot_account_name': bot.get('account_name') or None,
            'chat_id': chat_id or None,
            'polling_enabled': bool(settings.ZALO_POLLING_ENABLED),
            'zalo_webhook_registered': bool(str(webhook_info.get('url') or '').strip()),
            'zalo_webhook_url': webhook_info.get('url') or webhook_url,
            'public_base_url': public_base or None,
            'webhook_base_url': webhook_base or None,
            'webhook_path': ZALO_WEBHOOK_PATH,
            'webhook_origin_path': ZALO_WEBHOOK_ORIGIN_PATH,
            'webhook_url': webhook_url,
            'cloudflare_fix': {
                'problem': 'Zalo dùng User-Agent Java/1.8.0_192 cho webhook VÀ fetch ảnh sendPhoto — Cloudflare thường chặn GET/HEAD (403/1010)',
                'who_can_fix': 'Admin Cloudflare zone iotforce.io.vn',
                'recommended_fix': 'Redeploy deploy/cloudflare/zalo-platform-worker.js (route api/v1/zalo/webhook* + proxy GET webhook/media/*)',
                'cf_admin_option_webhook': 'Worker route: api-basondock.iotforce.io.vn/api/v1/zalo/webhook*',
                'cf_admin_option_media': 'Media URL mới: /api/v1/zalo/webhook/media/v/{code}.jpg (cùng Worker route webhook*)',
            },
            'webhook_secret_configured': bool(str(settings.ZALO_WEBHOOK_SECRET or '').strip()),
            'webhook_java_ua_probe': cf_check,
            'media_java_ua_probe': media_check,
            'media_url_prefix': '/api/v1/zalo/webhook/media',
            'register_webhook': 'POST /api/v1/zalo/webhook/register',
            'test_message': 'POST /api/v1/zalo/test-message',
            'test_unknown_notification': 'POST /api/v1/zalo/test-unknown-notification?detection_id=',
        }
    finally:
        db.close()


def register_webhook() -> dict[str, Any]:
    """Register webhook URL with Zalo Bot API (setWebhook)."""
    if not _zalo_enabled():
        raise ValueError('Zalo bot is not enabled or token is missing')

    webhook_base = _resolve_webhook_base_url()
    if not webhook_base.startswith('https://'):
        raise ValueError('ZALO_WEBHOOK_BASE_URL or ZALO_PUBLIC_BASE_URL must be a public HTTPS URL')

    secret = str(settings.ZALO_WEBHOOK_SECRET or '').strip()
    if len(secret) < 8:
        raise ValueError('ZALO_WEBHOOK_SECRET must be 8-256 characters')

    webhook_url = build_webhook_url()
    data = _call_zalo_api(
        'setWebhook',
        {
            'url': webhook_url,
            'secret_token': secret,
        },
    )
    return {
        'webhook_url': webhook_url,
        'zalo_response': data.get('result'),
    }


def ensure_zalo_startup() -> dict[str, Any]:
    """
    Called at app startup.
    Webhook mode (default): register setWebhook with Zalo.
    Polling mode: deleteWebhook + background getUpdates loop (started separately).
    """
    if not _zalo_enabled():
        return {'mode': 'disabled'}

    if settings.ZALO_POLLING_ENABLED:
        _log.info('Zalo mode: polling (webhook will be removed by polling service)')
        return {'mode': 'polling'}

    try:
        result = register_webhook()
        info = get_webhook_info()
        _log.info(
            'Zalo mode: webhook registered url=%s',
            info.get('url') or result.get('webhook_url'),
        )
        return {
            'mode': 'webhook',
            'webhook_url': result.get('webhook_url'),
            'zalo_webhook': info,
        }
    except Exception:
        _log.exception('Zalo webhook registration failed at startup')
        return {'mode': 'webhook', 'error': 'registration_failed'}


def get_webhook_info() -> dict[str, Any]:
    """Fetch current webhook configuration from Zalo."""
    if not _zalo_enabled():
        raise ValueError('Zalo bot is not enabled or token is missing')
    data = _call_zalo_api('getWebhookInfo', {})
    return data.get('result') or {}


def resolve_single_camera_image_path(db: Session, detection_id: int) -> Optional[str]:
    from app.repositories.detection_media_repository import detection_media_repo

    single: Optional[str] = None
    fallback: Optional[str] = None
    for row in detection_media_repo.get_by_detection(db, detection_id):
        path = str(row.file_path or '')
        if row.media_type != 'image' or not path:
            continue
        if 'single_overlay_in_' in path or 'single_best_detection_' in path:
            single = path
            break
        fallback = fallback or path
    if single:
        return single
    det = detection_repo.get(db, detection_id)
    audit = str(getattr(det, 'audit_image_path', '') or '') if det else ''
    if 'single_overlay_in_' in audit or 'single_best_detection_' in audit:
        return audit
    return fallback or audit or None


def resolve_detection_video_path(db: Session, detection_id: int) -> Optional[str]:
    from app.repositories.detection_media_repository import detection_media_repo

    single_video: Optional[str] = None
    fused_video: Optional[str] = None
    fallback: Optional[str] = None
    for row in detection_media_repo.get_by_detection(db, detection_id):
        if row.media_type != 'video':
            continue
        path = str(row.file_path or '')
        if not path:
            continue
        name = path.rsplit('/', 1)[-1]
        if name.startswith('single_') or '/videos/single_' in path:
            single_video = path
        elif name.startswith('fused_') or '/videos/fused_' in path:
            fused_video = fused_video or path
        fallback = fallback or path
    for candidate in (single_video, fused_video, fallback):
        if candidate and _minio_object_ready(candidate):
            return candidate
    det = detection_repo.get(db, detection_id)
    det_video = str(getattr(det, 'video_path', '') or '') if det else ''
    if det_video and _minio_object_ready(det_video):
        return det_video
    return None


def resolve_notification_media(
    db: Session, detection_id: int
) -> tuple[Optional[str], Optional[str]]:
    """Pick first MinIO-ready single-camera image and best available video."""
    image_candidates: list[str] = []
    single_image = resolve_single_camera_image_path(db, detection_id)
    if single_image:
        image_candidates.append(single_image)
    det = detection_repo.get(db, detection_id)
    if det is not None:
        audit = str(getattr(det, 'audit_image_path', '') or '')
        if audit and audit not in image_candidates:
            image_candidates.append(audit)

    from app.repositories.detection_media_repository import detection_media_repo

    for row in detection_media_repo.get_by_detection(db, detection_id):
        path = str(row.file_path or '')
        if row.media_type == 'image' and path and path not in image_candidates:
            image_candidates.append(path)

    image_path = next((p for p in image_candidates if _minio_object_ready(p)), None)
    video_path = resolve_detection_video_path(db, detection_id)
    return image_path, video_path


def send_test_unknown_notification(detection_id: int, *, force: bool = True) -> dict[str, Any]:
    if not _zalo_enabled():
        raise ValueError('Zalo bot is not enabled or token is missing')

    db = SessionLocal()
    try:
        det = detection_repo.get(db, detection_id)
        if not det:
            raise ValueError(f'Khong tim thay detection #{detection_id}')

        image_path, video_path = resolve_notification_media(db, detection_id)
        start_time = getattr(det, 'start_time', None)
        camera_name = 'Camera test'
    finally:
        db.close()

    notify_unknown_detection(
        detection_id=detection_id,
        camera_name=camera_name,
        start_time=start_time,
        force_resend=force,
    )
    image_url = _build_media_url(image_path)
    video_url = _build_media_url(video_path, video=True) if video_path else None
    return {
        'detection_id': detection_id,
        'image_minio_path': image_path,
        'video_minio_path': video_path,
        'image_url': image_url,
        'video_url': video_url,
        'image_url_zalo_reachable': _zalo_can_fetch_url(image_url) if image_url else False,
        'chat_id': get_resolved_chat_id(),
        'force_resend': force,
        'media_probe': check_media_java_ua_probe(),
    }
