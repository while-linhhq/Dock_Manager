"""Cảnh báo Zalo cho vi phạm neo đậu theo từng detection.

Ba loại độc lập, idempotent theo (detection_id, kind):
- registry_expired: tàu quá hạn đăng kiểm;
- outside_hours: khoảng neo chạm giờ không được phép;
- over_duration: một lượt neo vượt số phút tối đa.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.fee import FeeConfig
from app.models.zalo_notification import ZaloNotification
from app.repositories.detection_repository import detection_repo
from app.repositories.vessel_repository import vessel_repo
from app.utils.fee_operating_hours import (
    day_schedule_for_weekday,
    outside_operating_hours_for_interval,
    weekday_key_vn,
)

_log = logging.getLogger('app.services.berthing_alert')
VN_TZ = ZoneInfo('Asia/Ho_Chi_Minh')
UTC = ZoneInfo('UTC')

REGISTRY_EXPIRED_KIND = 'registry_expired'
OUTSIDE_HOURS_KIND = 'outside_hours'
OVER_DURATION_KIND = 'over_duration'

_WEEKDAY_LABELS = {
    'mon': 'Thứ 2',
    'tue': 'Thứ 3',
    'wed': 'Thứ 4',
    'thu': 'Thứ 5',
    'fri': 'Thứ 6',
    'sat': 'Thứ 7',
    'sun': 'Chủ nhật',
}


@dataclass(frozen=True)
class _Alert:
    kind: str
    caption: str


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _format_date(value: date | datetime | None) -> str:
    if value is None:
        return '-'
    if isinstance(value, datetime):
        value = value.date()
    return value.strftime('%d/%m/%Y')


def _format_time(value: datetime | None) -> str:
    value = _as_utc(value)
    return value.astimezone(VN_TZ).strftime('%H:%M %d/%m/%Y') if value else '-'


def _format_minutes(value: Decimal | int | None) -> str:
    if value is None:
        return '-'
    minutes = Decimal(str(value))
    hours = int(minutes // 60)
    remaining = minutes - Decimal(hours * 60)
    minute_text = f'{remaining.quantize(Decimal("0.01")):f}'.rstrip('0').rstrip('.')
    if hours and remaining:
        return f'{hours} giờ {minute_text} phút'
    if hours:
        return f'{hours} giờ'
    return f'{minute_text} phút'


def _format_schedule(operating_hours: dict, start: datetime | None) -> str:
    start = _as_utc(start)
    if start is None:
        return '-'
    weekday = weekday_key_vn(start)
    label = _WEEKDAY_LABELS.get(weekday, weekday)
    schedule = day_schedule_for_weekday(operating_hours, weekday)
    if not isinstance(schedule, dict):
        return f'{label}: không giới hạn'
    if schedule.get('closed') is True:
        return f'{label}: không cho phép neo'
    return f'{label}: {schedule.get("open", "-")}–{schedule.get("close", "-")}'


def _resolve_alert_fees(db, vessel) -> list[FeeConfig]:
    """Ưu tiên phí gắn tàu; fallback phí loại tàu để tương thích schema cũ."""
    query = db.query(FeeConfig).filter(FeeConfig.is_active.is_(True))
    vessel_id_column = getattr(FeeConfig, 'vessel_id', None)
    if vessel_id_column is not None:
        direct = query.filter(vessel_id_column == vessel.id).all()
        if direct:
            return direct
    vessel_type_id = getattr(vessel, 'vessel_type_id', None)
    if vessel_type_id is None:
        return []
    return query.filter(FeeConfig.vessel_type_id == vessel_type_id).all()


def _berth_duration_minutes(detection) -> Decimal | None:
    start = _as_utc(detection.berth_in_time or detection.start_time)
    end = _as_utc(detection.berth_out_time or detection.end_time)
    if start is None or end is None or end <= start:
        return None
    return (Decimal(str((end - start).total_seconds())) / Decimal('60')).quantize(
        Decimal('0.01')
    )


def _vessel_lines(vessel) -> list[str]:
    lines = [f'🚢 Mã tàu: {str(getattr(vessel, "ship_id", "") or "-")}']
    name = str(getattr(vessel, 'name', '') or '').strip()
    if name:
        lines.append(f'📛 Tên tàu: {name}')
    return lines


def _build_registry_caption(*, detection_id: int, vessel, expiry: date, start: datetime | None) -> str:
    lines = ['🛑 CẢNH BÁO: TÀU QUÁ HẠN ĐĂNG KIỂM NEO ĐẬU', *_vessel_lines(vessel)]
    lines.extend(
        [
            f'📅 Hết hạn đăng kiểm: {_format_date(expiry)}',
            f'🕐 Thời điểm vào: {_format_time(start)}',
            f'📋 Mã phát hiện: #{detection_id}',
            '',
            '⚠️ Vui lòng kiểm tra và xử lý.',
        ]
    )
    return '\n'.join(lines)[:2000]


def _build_outside_hours_caption(
    *,
    detection_id: int,
    vessel,
    start: datetime | None,
    end: datetime | None,
    outside_hours: Decimal,
    operating_hours: dict,
) -> str:
    lines = ['🟣 CẢNH BÁO: TÀU NEO NGOÀI GIỜ CHO PHÉP', *_vessel_lines(vessel)]
    lines.extend(
        [
            f'🕐 Bắt đầu neo: {_format_time(start)}',
            f'🕐 Kết thúc neo: {_format_time(end)}',
            f'⏱ Thời gian ngoài khung: {outside_hours.quantize(Decimal("0.01"))} giờ',
            f'🗓 Khung áp dụng: {_format_schedule(operating_hours, start)}',
            f'📋 Mã phát hiện: #{detection_id}',
            '',
            '⚠️ Vui lòng kiểm tra và xử lý.',
        ]
    )
    return '\n'.join(lines)[:2000]


def _build_over_duration_caption(
    *,
    detection_id: int,
    vessel,
    start: datetime | None,
    end: datetime | None,
    duration_minutes: Decimal,
    limit_minutes: int,
) -> str:
    lines = ['🟠 CẢNH BÁO: TÀU ĐẬU QUÁ THỜI GIAN MỘT LẦN CHO PHÉP', *_vessel_lines(vessel)]
    lines.extend(
        [
            f'🕐 Bắt đầu neo: {_format_time(start)}',
            f'🕐 Kết thúc neo: {_format_time(end)}',
            f'⏱ Thời gian thực tế: {_format_minutes(duration_minutes)}',
            f'⛔ Giới hạn một lần: {_format_minutes(limit_minutes)}',
            f'📋 Mã phát hiện: #{detection_id}',
            '',
            '⚠️ Vui lòng kiểm tra và xử lý.',
        ]
    )
    return '\n'.join(lines)[:2000]


def _collect_alerts(db, detection, vessel, *, today: date | None = None) -> list[_Alert]:
    """Tính các cảnh báo; không gửi và không ghi DB."""
    alerts: list[_Alert] = []
    detection_id = int(detection.id)
    start = _as_utc(detection.berth_in_time or detection.start_time)
    end = _as_utc(detection.berth_out_time or detection.end_time)

    expiry = getattr(vessel, 'registry_expiry', None)
    if isinstance(expiry, datetime):
        expiry = expiry.date()
    today = today or datetime.now(VN_TZ).date()
    if expiry is not None and expiry < today:
        alerts.append(
            _Alert(
                REGISTRY_EXPIRED_KIND,
                _build_registry_caption(
                    detection_id=detection_id,
                    vessel=vessel,
                    expiry=expiry,
                    start=start,
                ),
            )
        )

    fees = _resolve_alert_fees(db, vessel)

    outside_matches: list[tuple[Decimal, dict]] = []
    for fee in fees:
        operating_hours = getattr(fee, 'operating_hours', None)
        if not isinstance(operating_hours, dict):
            continue
        outside = outside_operating_hours_for_interval(start, end, operating_hours)
        if outside > 0:
            outside_matches.append((outside, operating_hours))
    if outside_matches:
        outside, operating_hours = max(outside_matches, key=lambda item: item[0])
        alerts.append(
            _Alert(
                OUTSIDE_HOURS_KIND,
                _build_outside_hours_caption(
                    detection_id=detection_id,
                    vessel=vessel,
                    start=start,
                    end=end,
                    outside_hours=outside,
                    operating_hours=operating_hours,
                ),
            )
        )

    duration = _berth_duration_minutes(detection)
    limits = [
        int(fee.max_berth_duration_minutes)
        for fee in fees
        if getattr(fee, 'max_berth_duration_minutes', None) is not None
        and int(fee.max_berth_duration_minutes) > 0
    ]
    if duration is not None and limits:
        limit = min(limits)
        if duration > Decimal(limit):
            alerts.append(
                _Alert(
                    OVER_DURATION_KIND,
                    _build_over_duration_caption(
                        detection_id=detection_id,
                        vessel=vessel,
                        start=start,
                        end=end,
                        duration_minutes=duration,
                        limit_minutes=limit,
                    ),
                )
            )

    return alerts


def _send_once(db, *, detection_id: int, alert: _Alert) -> bool:
    existing = (
        db.query(ZaloNotification)
        .filter(ZaloNotification.detection_id == detection_id)
        .filter(ZaloNotification.kind == alert.kind)
        .first()
    )
    if existing is not None:
        _log.info(
            'Skip Zalo berthing alert detection_id=%s kind=%s: already recorded status=%s',
            detection_id,
            alert.kind,
            existing.status,
        )
        return False

    from app.services import zalo_service

    chat_id = zalo_service.get_resolved_alert_chat_id()
    if not chat_id:
        _log.warning('Skip Zalo berthing alert detection_id=%s: chat ID missing', detection_id)
        return False

    row = ZaloNotification(
        detection_id=detection_id,
        chat_id=chat_id,
        status='pending_media',
        kind=alert.kind,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        _log.info(
            'Skip Zalo berthing alert detection_id=%s kind=%s: duplicate row',
            detection_id,
            alert.kind,
        )
        return False

    try:
        zalo_service.send_alert_text_message(chat_id, alert.caption)
        row.status = 'sent'
        db.commit()
        _log.info('Zalo berthing alert sent detection_id=%s kind=%s', detection_id, alert.kind)
        return True
    except Exception:
        row.status = 'failed'
        db.commit()
        _log.exception('Zalo berthing alert failed detection_id=%s kind=%s', detection_id, alert.kind)
        return False


def notify_berthing_alerts(detection_id: int) -> set[str]:
    """Gửi tất cả cảnh báo khớp; trả về tập kind đã gửi thành công."""
    if not (settings.ZALO_ENABLED and settings.ZALO_ALERT_BOT_TOKEN):
        return set()

    db = SessionLocal()
    try:
        detection = detection_repo.get(db, int(detection_id))
        if detection is None or not getattr(detection, 'vessel_id', None):
            return set()
        vessel = vessel_repo.get(db, int(detection.vessel_id))
        if vessel is None:
            return set()

        sent: set[str] = set()
        for alert in _collect_alerts(db, detection, vessel):
            if _send_once(db, detection_id=int(detection_id), alert=alert):
                sent.add(alert.kind)
        return sent
    finally:
        db.close()


def notify_if_registry_expired(detection_id: int) -> None:
    """Backward-compatible entry point; generic service now checks all three rules."""
    notify_berthing_alerts(detection_id)


def schedule_berthing_alerts(detection_id: int) -> None:
    """Chạy nền để không chặn pipeline persist."""
    if not (settings.ZALO_ENABLED and settings.ZALO_ALERT_BOT_TOKEN):
        return
    threading.Thread(
        target=notify_berthing_alerts,
        args=(int(detection_id),),
        daemon=True,
        name=f'zalo-berthing-alert-{int(detection_id)}',
    ).start()


def schedule_registry_expiry_notify(detection_id: int) -> None:
    """Backward-compatible alias."""
    schedule_berthing_alerts(detection_id)
