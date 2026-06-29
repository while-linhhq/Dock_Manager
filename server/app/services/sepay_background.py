import asyncio
import logging

from sqlalchemy.exc import DBAPIError, OperationalError

from app.db.session import SessionLocal
from app.services.sepay_config_service import get_sepay_config
from app.services.sepay_sync_service import sync_sepay_payments

logger = logging.getLogger('app.sepay.background')

_task: asyncio.Task | None = None


def _sync_once() -> int:
    """Run one SEPay sync cycle; return next interval (seconds)."""
    db = SessionLocal()
    try:
        cfg = get_sepay_config(db)
        if cfg.api_token:
            result = sync_sepay_payments(db)
            if result.get('recorded'):
                logger.info('SEPay background sync: %s', result)
        return cfg.sync_interval_sec
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


async def _sync_loop() -> None:
    interval = 30
    while True:
        try:
            interval = _sync_once()
        except (OperationalError, DBAPIError) as exc:
            logger.warning('SEPay sync: DB connection error (%s), retrying once', exc)
            try:
                interval = _sync_once()
            except Exception:
                logger.exception('SEPay background sync error')
        except Exception:
            logger.exception('SEPay background sync error')

        await asyncio.sleep(interval)


def start_sepay_background_sync() -> None:
    global _task
    if _task is not None and not _task.done():
        return
    _task = asyncio.create_task(_sync_loop(), name='sepay-sync')


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
