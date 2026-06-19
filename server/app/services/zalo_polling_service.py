"""Long-polling fallback when Cloudflare blocks Zalo webhook (User-Agent Java/1.8.0_192)."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.core.config import settings
from app.services import zalo_service

_log = logging.getLogger('app.services.zalo_polling')

_task: asyncio.Task | None = None
_POLL_TIMEOUT_SEC = 25


def _iter_update_events(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize getUpdates / webhook payloads into a list of event dicts."""
    result = data.get('result') if isinstance(data, dict) else None
    if isinstance(result, list):
        events: list[dict[str, Any]] = []
        for item in result:
            if not isinstance(item, dict):
                continue
            normalized = zalo_service._normalize_event_result(item)
            events.append(normalized if normalized else item)
        return events
    if isinstance(result, dict) and result.get('event_name'):
        return [result]
    if isinstance(data, dict) and data.get('event_name'):
        return [data]
    return []


async def _poll_loop() -> None:
    _log.info('Zalo polling started (webhook disabled on Zalo side)')
    try:
        zalo_service._call_zalo_api('deleteWebhook', {})
    except Exception:
        _log.exception('Zalo deleteWebhook failed at polling start')

    while True:
        if not zalo_service._zalo_enabled():
            _log.warning('Zalo polling stopped: bot disabled or token missing')
            break
        try:
            data = await asyncio.to_thread(
                zalo_service._call_zalo_api_allow_timeout,
                'getUpdates',
                {'timeout': str(_POLL_TIMEOUT_SEC)},
            )
            for event in _iter_update_events(data):
                zalo_service.process_incoming_payload({'ok': True, 'result': event})
        except asyncio.CancelledError:
            raise
        except Exception:
            _log.exception('Zalo polling iteration failed')
        await asyncio.sleep(0.5)


def start_zalo_polling() -> None:
    global _task
    if not settings.ZALO_ENABLED or not settings.ZALO_POLLING_ENABLED:
        return
    if _task is not None and not _task.done():
        return
    _task = asyncio.create_task(_poll_loop(), name='zalo-polling')
    _log.info('Zalo polling background task scheduled')


async def stop_zalo_polling() -> None:
    global _task
    if _task is None:
        return
    _task.cancel()
    try:
        await _task
    except asyncio.CancelledError:
        pass
    _task = None
    _log.info('Zalo polling background task stopped')
