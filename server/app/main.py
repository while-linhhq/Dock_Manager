import os
import sys

_server_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _server_root not in sys.path:
    sys.path.insert(0, _server_root)

# Cap OMP/MKL/OpenBLAS thread pools BEFORE numpy/torch/cv2 are imported
# (they read these env vars at import time). Stops CPU oversubscription.
from app.utils.ai.thread_limits import apply_thread_env_caps

apply_thread_env_caps()

from app.utils.ai.gpu_bootstrap import init_cuda_library_path

init_cuda_library_path('pre')

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from jose import jwt
from app.api.v1.router import api_router
from app.core.config import settings
from app.db.session import SessionLocal
from app.repositories.audit_log_repository import audit_log_repo
import logging
import sys
import time
from logging.config import dictConfig

def _configure_logging() -> None:
    level = str(getattr(settings, 'LOG_LEVEL', 'INFO') or 'INFO').upper()

    handlers: dict = {
        'console': {
            'class': 'logging.StreamHandler',
            'stream': sys.stdout,
            'formatter': 'default',
        },
    }
    root_handlers = ['console']

    # Optional rotating file handler so the "Xem Logs" page has a source to tail.
    if bool(getattr(settings, 'LOG_TO_FILE', False)):
        import os

        log_path = str(getattr(settings, 'LOG_FILE_PATH', 'logs/app.log') or 'logs/app.log')
        if not os.path.isabs(log_path):
            # Resolve relative to the server root (parent of the app package).
            log_path = os.path.join(_server_root, log_path)
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        handlers['file'] = {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': log_path,
            'maxBytes': int(getattr(settings, 'LOG_FILE_MAX_BYTES', 10 * 1024 * 1024)),
            'backupCount': int(getattr(settings, 'LOG_FILE_BACKUP_COUNT', 5)),
            'encoding': 'utf-8',
            'formatter': 'default',
        }
        root_handlers.append('file')

    dictConfig(
        {
            'version': 1,
            'disable_existing_loggers': False,
            'formatters': {
                'default': {
                    'format': '%(asctime)s %(levelname)s [%(name)s] %(message)s',
                },
            },
            'handlers': handlers,
            'root': {
                'level': level,
                'handlers': root_handlers,
            },
            'loggers': {
                # Keep uvicorn logs visible and consistent
                'uvicorn': {'level': level},
                'uvicorn.error': {'level': level},
                'uvicorn.access': {'level': level},
                # Our app logs
                'app': {'level': level},
                'app.startup': {'level': level, 'propagate': True},
                # Third-party HTTP clients spam one INFO line per request
                # ("HTTP Request: POST .../points/search" from every Qdrant
                # embedding search). Cap at WARNING so the log stays readable.
                'httpx': {'level': 'WARNING'},
                'httpcore': {'level': 'WARNING'},
                'urllib3': {'level': 'WARNING'},
                'qdrant_client': {'level': 'WARNING'},
            },
        }
    )


_configure_logging()
logger = logging.getLogger('app.main')
access_logger = logging.getLogger('app.api.access')


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.core.startup_report import run_startup_checks

    try:
        run_startup_checks()
    except Exception:
        logger.exception('Startup checks failed')
        raise

    from app.core.config import settings as app_settings

    if app_settings.SEPAY_SYNC_ENABLED:
        from app.services.sepay_background import start_sepay_background_sync

        start_sepay_background_sync()

    if app_settings.ZALO_ENABLED:
        if app_settings.ZALO_POLLING_ENABLED:
            from app.services.zalo_polling_service import start_zalo_polling

            start_zalo_polling()
        else:
            from app.services.zalo_service import ensure_zalo_startup

            ensure_zalo_startup()

    from app.services.ai.ship_id_rule_engine import start_rule_engine_daemon

    start_rule_engine_daemon(interval_s=30)

    # torch/cv2 are imported by now; cap their thread pools too.
    from app.utils.ai.thread_limits import apply_runtime_thread_caps

    apply_runtime_thread_caps()

    yield

    if app_settings.ZALO_ENABLED and app_settings.ZALO_POLLING_ENABLED:
        from app.services.zalo_polling_service import stop_zalo_polling

        await stop_zalo_polling()

    if app_settings.SEPAY_SYNC_ENABLED:
        from app.services.sepay_background import stop_sepay_background_sync

        await stop_sepay_background_sync()
    from app.services.pipeline_service import pipeline_service

    from app.core.startup_report import log_shutdown

    log_shutdown()
    if pipeline_service.is_running:
        logger.info('Stopping AI pipeline before process exit')
        try:
            pipeline_service.stop()
        except Exception:
            logger.exception('Pipeline stop failed during shutdown')


app = FastAPI(title=settings.PROJECT_NAME, version='0.1.0', lifespan=lifespan)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify the actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware('http')
async def audit_http_requests(request: Request, call_next):
    started_monotonic = time.perf_counter()
    response = None
    skip_audit = False
    try:
        response = await call_next(request)
        return response
    finally:
        path = request.url.path or ''
        method = request.method.upper()
        status_code = response.status_code if response is not None else 500
        duration_ms = int((time.perf_counter() - started_monotonic) * 1000)
        if path.startswith('/api/v1'):
            access_logger.info(
                '%s %s%s -> %s %sms client=%s',
                method,
                path,
                f'?{request.url.query}' if request.url.query else '',
                status_code,
                duration_ms,
                request.client.host if request.client else '-',
            )

        if not path.startswith('/api/v1'):
            skip_audit = True
        if path.startswith('/api/v1/auth/login'):
            skip_audit = True
        # Persist only mutating API calls; skip GET/HEAD/OPTIONS (read noise)
        if path.startswith('/api/v1') and method in (
            'GET',
            'HEAD',
            'OPTIONS',
        ):
            skip_audit = True

        if not skip_audit:
            user_id = None
            auth_header = request.headers.get('authorization', '')
            if auth_header.lower().startswith('bearer '):
                token = auth_header.split(' ', 1)[1].strip()
                if token:
                    try:
                        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
                        raw_sub = payload.get('sub')
                        if raw_sub is not None:
                            user_id = int(raw_sub)
                    except Exception:
                        user_id = None

            action_map = {
                'POST': 'CREATE',
                'PUT': 'UPDATE',
                'PATCH': 'UPDATE',
                'DELETE': 'DELETE',
                'GET': 'READ',
            }
            action = action_map.get(method, method)

            segments = [seg for seg in path.strip('/').split('/') if seg]
            entity_type = 'system'
            entity_id = None
            if len(segments) >= 3:
                entity_type = segments[2]
            if len(segments) >= 4:
                try:
                    entity_id = int(segments[3])
                except Exception:
                    entity_id = None

            details = {
                'method': method,
                'path': path,
                'status_code': status_code,
                'query': str(request.url.query or ''),
                'duration_ms': duration_ms,
                'user_agent': request.headers.get('user-agent', ''),
            }

            db = SessionLocal()
            try:
                audit_log_repo.create(
                    db,
                    {
                        'user_id': user_id,
                        'action': action,
                        'entity_type': entity_type,
                        'entity_id': entity_id,
                        'details': details,
                        'ip_address': request.client.host if request.client else None,
                    },
                )
            except Exception:
                logger.exception('audit middleware failed to write log')
            finally:
                db.close()

# Force reload of api_router to ensure all routes are captured
app.include_router(api_router, prefix="/api/v1")

@app.get("/")
async def root():
    return {"message": f"Welcome to {settings.PROJECT_NAME}"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
