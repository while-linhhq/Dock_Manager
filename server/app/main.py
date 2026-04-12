from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.router import api_router
from app.core.config import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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

# Force reload of api_router to ensure all routes are captured
app.include_router(api_router, prefix="/api/v1")

@app.get("/")
async def root():
    return {"message": f"Welcome to {settings.PROJECT_NAME}"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
