import asyncio
import logging

from app.db.session import SessionLocal
from app.services.sepay_config_service import get_sepay_config
from app.services.sepay_sync_service import sync_sepay_payments

logger = logging.getLogger('app.sepay.background')

_task: asyncio.Task | None = None


async def _sync_loop() -> None:
    interval = 30
    while True:
        db = SessionLocal()
        try:
            cfg = get_sepay_config(db)
            interval = cfg.sync_interval_sec
            if cfg.api_token:
                result = sync_sepay_payments(db)
                if result.get('recorded'):
                    logger.info('SEPay background sync: %s', result)
        except Exception:
            logger.exception('SEPay background sync error')
        finally:
            db.close()

        await asyncio.sleep(interval)


def start_sepay_background_sync() -> None:
    global _task
    if _task is not None and not _task.done():
        return
    _task = asyncio.create_task(_sync_loop(), name='sepay-sync')
    logger.info('SEPay background sync task started')


async def stop_sepay_background_sync() -> None:
    global _task
    if _task is None:
        return
    _task.cancel()
    try:
        await _task
    except asyncio.CancelledError:
        pass
    _task = None
    logger.info('SEPay background sync task stopped')
