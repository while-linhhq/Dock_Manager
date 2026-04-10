from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "FastAPI Bason Ship Detection"
    DATABASE_URL: str = "postgresql://user:password@localhost:5432/db_name"
    SECRET_KEY: str = "secret"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Model settings
    MODEL_PATH: str = "app/yolo11n.pt"
    DEVICE: str = "0"
    CONF: float = 0.75
    RESIZE_SCALE: float = 0.5
    
    # Boat tracker (IoU + state machine)
    TRACK_MIN_HITS: int = 30
    TRACK_MAX_TENTATIVE_MISSES: int = 10
    TRACK_MAX_LOST_FRAMES: int = 80
    TRACK_IOU_THRESHOLD: float = 0.3
    
    # Re-ID & Dedup logic
    TRACK_REID_WINDOW_SEC: float = 120.0
    TRACK_REID_MAX_DIST: float = 150.0
    
    # OCR / Paddle configuration
    OCR_INTERVAL_FRAMES: int = 10
    ENABLE_OCR: bool = True
    OCR_LABEL_TTL_SEC: float = 5.0
    SAVE_MIN_INTERVAL_SEC: float = 20.0
    OCR_AUDIT_ENABLE: bool = True
    OCR_AUDIT_SAVE_FRAMES: bool = True
    
    # Video record configuration
    RECORD_ENABLE: bool = True
    RECORD_MAX_DURATION_MIN: int = 5
    RECORD_NO_BOAT_GAP_SEC: int = 20
    RECORD_FPS: int = 20

    model_config = SettingsConfigDict(
        env_file='.env',
        extra='ignore',
    )

settings = Settings()
