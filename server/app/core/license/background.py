"""Vòng check-in license định kỳ chạy nền (giống ``sepay_background.py``).

Lifespan khởi động task sau khi ``license_service.initialize()``; mỗi chu kỳ
``LICENSE_CHECKIN_HOURS`` gọi ``license_service.verify_now()`` trong thread
riêng (``asyncio.to_thread``) để HTTP Keygate không block event loop. Lỗi một
chu kỳ không làm chết vòng lặp: log lại rồi thử lại sau ``min(300, interval)``
giây. Dừng app thì cancel task và chờ nó kết thúc.
"""
from __future__ import annotations

import asyncio
import logging
import math

from app.core.config import settings
from app.core.license.service import license_service

logger = logging.getLogger('app.license.background')

_task: asyncio.Task | None = None


def _interval_seconds() -> float:
    """Chu kỳ check-in (giây) từ ``LICENSE_CHECKIN_HOURS``.

    Giá trị 0/âm/không hữu hạn rơi về mặc định 6h (không phải 1 giây) để cấu
    hình hỏng không biến vòng lặp thành busy-loop.
    """
    try:
        hours = float(settings.LICENSE_CHECKIN_HOURS)
    except (TypeError, ValueError):
        hours = 6.0
    if not math.isfinite(hours) or hours <= 0:
        hours = 6.0
    return max(hours * 3600.0, 1.0)


async def _checkin_loop() -> None:
    """Verify license mỗi chu kỳ; lỗi tạm thời chỉ trì hoãn chu kỳ kế tiếp."""
    while True:
        interval = _interval_seconds()
        # Lazy init retry: lần boot đầu có thể fail (DB chưa sẵn sàng); thử lại
        # trước mỗi verify thay vì để service kẹt ở fallback mãi mãi.
        try:
            if not license_service.is_initialized():
                license_service.initialize()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception('License background initialization retry failed')
            await asyncio.sleep(min(300.0, interval))
            continue
        try:
            await asyncio.to_thread(license_service.verify_now)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception('License background check-in error')
            interval = min(300.0, interval)
        await asyncio.sleep(interval)


def start_license_background() -> None:
    """Tạo task check-in nếu chưa có (gọi trong lifespan, cần event loop)."""
    global _task
    if _task is not None and not _task.done():
        return
    _task = asyncio.create_task(_checkin_loop(), name='license-checkin')
    logger.info('License background check-in started')


async def stop_license_background() -> None:
    """Cancel task check-in và chờ nó kết thúc (gọi khi shutdown)."""
    global _task
    if _task is None:
        return
    _task.cancel()
    try:
        await _task
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception('License background check-in task failed during shutdown')
    _task = None
    logger.info('License background check-in task stopped')
