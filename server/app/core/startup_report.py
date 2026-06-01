"""Structured, concise startup diagnostics for FastAPI lifespan."""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from sqlalchemy import text

from app.core.config import settings
from app.db.session import engine

log = logging.getLogger('app.startup')

_BANNER = '─' * 52


def _mask_db_url(url: str) -> str:
    try:
        p = urlparse(url)
        host = p.hostname or '?'
        port = f':{p.port}' if p.port else ''
        db = (p.path or '/').lstrip('/') or '?'
        user = p.username or '?'
        return f'{user}@{host}{port}/{db}'
    except Exception:
        return '(invalid DATABASE_URL)'


def _ok(label: str, detail: str) -> None:
    log.info('  ✓ %-10s %s', label, detail)


def _fail(label: str, detail: str) -> None:
    log.error('  ✗ %-10s %s', label, detail)


def _check_database() -> bool:
    label = 'Database'
    target = _mask_db_url(settings.DATABASE_URL)
    try:
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
        _ok(label, f'connected ({target})')
        return True
    except Exception as exc:
        _fail(label, f'{target} — {exc}')
        return False


def _run_schema_patches() -> list[str]:
    from app.db.schema_patches import apply_schema_patches

    applied = apply_schema_patches(quiet=True)
    if applied:
        log.info('  · Schema     %d patch(es): %s', len(applied), '; '.join(applied))
    else:
        _ok('Schema', 'up to date (no patches applied)')
    return applied


def _check_minio() -> bool:
    from app.services.storage.minio_probe import probe_minio

    label = 'MinIO'
    endpoint = str(getattr(settings, 'MINIO_ENDPOINT', '') or '').strip() or '?'
    bucket = str(getattr(settings, 'MINIO_BUCKET', '') or 'media')
    prefix = str(getattr(settings, 'MINIO_MEDIA_PREFIX', '') or '').strip()
    layout_root = f'{prefix}/detections/' if prefix else 'detections/'

    try:
        summary = probe_minio(list_prefix=layout_root, max_list=500)
        counts = summary.get('counts') or {}
        final_n = int(counts.get('final', 0))
        legacy_n = int(counts.get('legacy', 0))
        staging_n = int(counts.get('staging_video', 0))
        listed = int(summary.get('listed', 0))

        _ok(
            label,
            f'{endpoint}  bucket={bucket}  prefix={layout_root}',
        )
        log.info(
            '             objects ~%s (sampled) · layout final=%s legacy=%s staging=%s',
            listed,
            final_n,
            legacy_n,
            staging_n,
        )
        if staging_n > 0 and final_n == 0:
            log.warning(
                '             staging videos present but no final paths — check pipeline finalize',
            )
        return True
    except Exception as exc:
        _fail(label, f'{endpoint} bucket={bucket} — {exc}')
        return False


def _log_sepay() -> None:
    if not settings.SEPAY_SYNC_ENABLED:
        _ok('SEPay', 'background sync disabled (SEPAY_SYNC_ENABLED=false)')
        return
    interval = int(getattr(settings, 'SEPAY_SYNC_INTERVAL_SEC', 30) or 30)
    token_ok = bool(str(getattr(settings, 'SEPAY_API_TOKEN', '') or '').strip())
    detail = f'every {interval}s'
    if token_ok:
        detail += ', API token set'
    else:
        detail += ', no API token (sync idle until configured)'
    _ok('SEPay', detail)


def _log_runtime() -> None:
    _ok('Runtime', f'LOG_LEVEL={settings.LOG_LEVEL}  DEVICE={settings.DEVICE}')
    model = str(getattr(settings, 'MODEL_PATH', '') or '')
    if model:
        log.info('             AI model %s', model)


def run_startup_checks() -> None:
    """Run all startup probes; log a compact block. Raises if DB or schema patches fail."""
    log.info(_BANNER)
    log.info('  Dock Manager API — startup')
    log.info(_BANNER)

    if not _check_database():
        raise RuntimeError('Database connection failed')

    _run_schema_patches()
    _check_minio()
    _log_sepay()
    _log_runtime()

    log.info(_BANNER)
    log.info('  Ready — %s', settings.PROJECT_NAME)
    log.info(_BANNER)


def log_shutdown() -> None:
    log.info('  Shutting down…')
