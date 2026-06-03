from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal

class Settings(BaseSettings):
    PROJECT_NAME: str = "FastAPI Bason Ship Detection"
    DATABASE_URL: str = "postgresql://user:password@localhost:5432/db_name"
    SECRET_KEY: str = "secret"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # MinIO (Object Storage) for detection media — API :9100, Console UI :9101 (docker-compose)
    MINIO_ENDPOINT: str = "127.0.0.1:9100"
    MINIO_ACCESS_KEY: str = "minio"
    MINIO_SECRET_KEY: str = "minio123456"
    MINIO_BUCKET: str = "media"
    MINIO_SECURE: bool = False
    MINIO_MEDIA_PREFIX: str = ""  # optional prefix inside bucket, e.g. "prod"
    MINIO_UPLOAD_ON_DETECT: bool = True
    
    # Model settings
    MODEL_PATH: str = "app/yolo11n.pt"
    DEVICE: str = "0"
    CONF: float = 0.75
    RESIZE_SCALE: float = 0.5
    
    # Boat tracker (IoU + state machine) — timing in seconds (see port_timing_config)
    TRACK_MIN_CONFIRM_SEC: float = 1.5
    TRACK_MAX_TENTATIVE_SEC: float = 0.5
    TRACK_MAX_LOST_SEC: float = 4.0
    TRACK_IOU_THRESHOLD: float = 0.3
    
    # Re-ID & Dedup logic
    TRACK_REID_WINDOW_SEC: float = 120.0
    TRACK_REID_MAX_DIST: float = 150.0
    REID_EMBEDDING_MODEL_PATH: str = ""
    REID_VISUAL_THRESHOLD: float = 0.6
    REID_HANDOFF_WINDOW_SEC: float = 30.0
    PRIMARY_ZONE_RATIO: float = 0.8
    EDGE_ZONE_RATIO: float = 0.1
    CLAHE_CLIP_LIMIT: float = 3.0
    CLAHE_TILE_SIZE: int = 8
    FUSED_FRAME_MAX_WIDTH: int = 1280
    FUSED_FRAME_MAX_HEIGHT: int = 720
    PREVIEW_MAX_WIDTH: int = 960
    PREVIEW_MAX_HEIGHT: int = 540

    # OCR / Paddle configuration
    OCR_INTERVAL_SEC: float = 0.5
    ENABLE_OCR: bool = True
    OCR_LABEL_TTL_SEC: float = 5.0
    SAVE_MIN_INTERVAL_SEC: float = 20.0
    OCR_AUDIT_ENABLE: bool = True
    OCR_AUDIT_SAVE_FRAMES: bool = True
    
    # Video record configuration
    RECORD_ENABLE: bool = True
    RECORD_MAX_DURATION_MIN: int = 5
    RECORD_NO_BOAT_GAP_SEC: int = 20
    # Single FPS for RTSP read, AI, dashboard preview, and video record (port_configs: record_fps).
    RECORD_FPS: int = 20

    # Video transcode (ensure browser-playable MP4)
    VIDEO_TRANSCODE_ENABLE: bool = True
    VIDEO_TRANSCODE_PRESET: str = "veryfast"
    VIDEO_TRANSCODE_CRF: int = 23

    # Seam Anchor (mooring persistence at camera seams)
    SEAM_ANCHOR_ENABLED: bool = True
    SEAM_ROI_WIDTH_RATIO: float = 0.15
    SEAM_PROXIMITY_PX: int = 40
    BG_SUBTRACT_THRESHOLD: float = 0.18
    BG_MODEL_HISTORY: int = 500
    BG_VAR_THRESHOLD: float = 25.0
    BG_MIN_SEED_FRAMES: int = 100
    ANCHOR_IOU_RESURRECT_THRESHOLD: float = 0.3
    ANCHOR_EMBEDDING_MATCH_ENABLED: bool = True
    ANCHOR_EMBEDDING_SIM_THRESHOLD: float = 0.65
    ANCHOR_REVALIDATION_SEC: float = 5.0
    ANCHOR_DEPARTED_GRACE_SEC: float = 30.0
    ANCHOR_MAX_DURATION_SEC: float = 172800.0
    ANCHOR_DB_UPDATE_DEBOUNCE_SEC: float = 30.0
    ANCHOR_MIN_STATIONARY_SEC: float = 8.0
    ANCHOR_COLOR_HSV_TOLERANCE_H: int = 15

    # Visual ID (ViT + vector search)
    ENABLE_VISUAL_ID: bool = True
    VISUAL_ID_INTERVAL_SEC: float = 1.0
    VISUAL_MIN_CROP_AREA: int = 4096
    VISUAL_MATCH_THRESHOLD: float = 0.72
    VISUAL_MARGIN_THRESHOLD: float = 0.04
    VISUAL_TOP_K: int = 5
    VISUAL_MODEL_PATH: str = ""
    VISUAL_BACKBONE: str = "vit_base_patch16_224"
    VISUAL_EMBEDDING_DIM: int = 768
    VISUAL_BATCH_SIZE: int = 8
    VISUAL_DEVICE: str = "0"

    # Redis cache
    REDIS_URL: str = "redis://127.0.0.1:6379/0"
    REDIS_KEY_PREFIX: str = "dock_manager"
    REDIS_VISUAL_TTL_SEC: int = 300

    # Qdrant vector DB
    QDRANT_HOST: str = "127.0.0.1"
    QDRANT_PORT: int = 6333
    QDRANT_API_KEY: str = ""
    QDRANT_COLLECTION: str = "vessel_visual_embeddings"
    QDRANT_VECTOR_SIZE: int = 768
    QDRANT_DISTANCE: str = "COSINE"

    # Training snapshot collection (crop saves for model training)
    ENABLE_TRAINING_SNAPSHOT: bool = False
    TRAINING_SNAPSHOT_INTERVAL_SEC: float = 5.0
    TRAINING_SNAPSHOT_BASE_DIR: str = "snapshot"
    TRAINING_SNAPSHOT_JPEG_QUALITY: int = 95

    # SEPay (bank transfer QR + API sync)
    SEPAY_API_TOKEN: str = ''
    SEPAY_CRON_SECRET: str = ''
    SEPAY_SYNC_INTERVAL_SEC: int = 30
    SEPAY_SYNC_ENABLED: bool = True
    SEPAY_BANK_ACCOUNT: str = ''
    SEPAY_BANK_NAME: str = ''
    SEPAY_ACCOUNT_NAME: str = ''

    # Logging
    LOG_LEVEL: Literal['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG'] = 'INFO'

    model_config = SettingsConfigDict(
        env_file='.env',
        extra='ignore',
    )

settings = Settings()
