from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from jose import jwt
from app.api.v1.router import api_router
from app.core.config import settings
from app.db.session import SessionLocal
from app.repositories.audit_log_repository import audit_log_repo
import logging
import sys
from logging.config import dictConfig

def _configure_logging() -> None:
    level = str(getattr(settings, 'LOG_LEVEL', 'INFO') or 'INFO').upper()
    dictConfig(
        {
            'version': 1,
            'disable_existing_loggers': False,
            'formatters': {
                'default': {
                    'format': '%(asctime)s %(levelname)s [%(name)s] %(message)s',
                },
            },
            'handlers': {
                'console': {
                    'class': 'logging.StreamHandler',
                    'stream': sys.stdout,
                    'formatter': 'default',
                },
            },
            'root': {
                'level': level,
                'handlers': ['console'],
            },
            'loggers': {
                # Keep uvicorn logs visible and consistent
                'uvicorn': {'level': level},
                'uvicorn.error': {'level': level},
                'uvicorn.access': {'level': level},
                # Our app logs
                'app': {'level': level},
            },
        }
    )


_configure_logging()
logger = logging.getLogger('app.main')


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.db.schema_patches import apply_schema_patches

    try:
        apply_schema_patches()
    except Exception:
        logger.exception('Schema patches failed — fix DB or run app/db/add_invoice_deleted_at.sql')
        raise
    yield


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
    started_at = datetime.now(timezone.utc)
    response = None
    skip_audit = False
    try:
        response = await call_next(request)
        return response
    finally:
        path = request.url.path or ''
        if not path.startswith('/api/v1'):
            skip_audit = True
        if path.startswith('/api/v1/auth/login'):
            skip_audit = True
        # Persist only mutating API calls; skip GET/HEAD/OPTIONS (read noise)
        if path.startswith('/api/v1') and request.method.upper() in (
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

            method = request.method.upper()
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

            status_code = response.status_code if response is not None else 500
            details = {
                'method': method,
                'path': path,
                'status_code': status_code,
                'query': str(request.url.query or ''),
                'duration_ms': int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000),
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
app.mount("/runs", StaticFiles(directory="runs", check_dir=False), name="runs")

@app.get("/")
async def root():
    return {"message": f"Welcome to {settings.PROJECT_NAME}"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
