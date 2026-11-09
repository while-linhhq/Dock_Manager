from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal

class Settings(BaseSettings):
    PROJECT_NAME: str = "FastAPI Bason Ship Detection"
    DATABASE_URL: str = "postgresql://user:password@localhost:5432/db_name"
    SECRET_KEY: str = "secret"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # MinIO (Object Storage) for detection media — API :9100, Console UI :9101 (docker-compose)
    MINIO_ENDPOINT: str = "127.0.0.1:9100"
    MINIO_ACCESS_KEY: str = "minio"
    MINIO_SECRET_KEY: str = "minio123456"
    MINIO_BUCKET: str = "media"
    MINIO_SECURE: bool = False
    MINIO_MEDIA_PREFIX: str = ""  # optional prefix inside bucket, e.g. "prod"
    MINIO_UPLOAD_ON_DETECT: bool = True

    # AWS S3 (replaces MinIO in production)
    AWS_REGION: str = "us-east-1"
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    # Endpoint S3 tường minh. Trỏ MinIO local (mặc định) — đặt rỗng để dùng AWS thật.
    # boto3 chỉ đọc biến môi trường, không đọc .env, nên s3_service truyền giá trị
    # này vào client để chạy local không cần export gì thêm.
    AWS_ENDPOINT_URL: str = "http://127.0.0.1:9100"
    # Base công khai để dựng URL media mở được từ trình duyệt ở xa (ảnh đối chiếu,
    # video). Để trống thì lấy ZALO_PUBLIC_BASE_URL, rồi mới tới origin của request.
    PUBLIC_BASE_URL: str = ""
    
    # Model settings — toàn bộ model AI nằm trong server/models/
    # (xem scripts/export_engines.py để build lại engine trên từng máy)
    MODEL_DIR: str = "models"
    MODEL_PATH: str = "models/yolo/yolo26s_finetuned.pt"
    # Ưu tiên TensorRT engine cùng tên (.pt → .engine) nếu có. Engine gắn cứng GPU
    # arch + phiên bản TensorRT nên KHÔNG bê sang máy khác được → luôn có đường lùi .pt.
    YOLO_PREFER_ENGINE: bool = True
    DEVICE: str = "0"
    CONF: float = 0.75
    YOLO_IMGSZ: int = 640
    RESIZE_SCALE: float = 0.5
    
    # Boat tracker (IoU + state machine) — timing in seconds (see port_timing_config)
    TRACK_MIN_CONFIRM_SEC: float = 1.5
    TRACK_MAX_TENTATIVE_SEC: float = 0.5
    TRACK_MAX_LOST_SEC: float = 4.0
    TRACK_IOU_THRESHOLD: float = 0.3
    # Lọc bbox trùng cho CÙNG một track: nếu 2 detection box chồng nhau với
    # IoMin (giao / diện tích box nhỏ hơn) >= ngưỡng này thì bỏ box conf thấp
    # trước khi đưa vào tracker (bắt trường hợp box lồng nhau mà NMS IoU bỏ sót).
    # 0 = tắt lọc.
    TRACK_DEDUP_IOMIN_THRESHOLD: float = 0.0
    # Bỏ qua track có thời gian neo đậu (berth_out-berth_in, fallback dwell
    # last_seen-first_seen) nhỏ hơn ngưỡng này (giây). 0 = tắt lọc.
    TRACK_MIN_BERTH_DURATION_SEC: float = 0.0
    BERTH_MERGE_GAP_SEC: float = 1800.0
    DETECTION_MERGE_WINDOW_HOURS: float = 2.0
    BERTH_MERGE_SKIP_UNKNOWN: bool = True
    # Thời gian ân hạn (giây) trước khi chốt tín hiệu OUT: khi tàu vượt ra ngoài
    # vùng neo, OUT chỉ được xác nhận nếu tàu ở NGOÀI liên tục >= ngưỡng này.
    # Nếu tàu vào lại vùng trong thời gian ân hạn (đang căn góc/lùi neo) thì OUT
    # bị hủy (unlock), berth_out không bị chốt sai → tránh tính sai thời gian và
    # chi phí. 0 = tắt (chốt OUT ngay khi vượt ngưỡng, như cũ).
    BERTH_OUT_GRACE_SEC: float = 0.0
    
    # Re-ID & Dedup logic
    TRACK_REID_WINDOW_SEC: float = 120.0
    TRACK_REID_MAX_DIST: float = 150.0
    REID_EMBEDDING_MODEL_PATH: str = ""
    REID_VISUAL_THRESHOLD: float = 0.6
    REID_HANDOFF_WINDOW_SEC: float = 30.0
    PRIMARY_ZONE_RATIO: float = 0.8
    EDGE_ZONE_RATIO: float = 0.1
    # Concurrent overlap merge (cross-camera Re-ID Phần 2)
    REID_OVERLAP_MERGE_ENABLED: bool = True
    REID_EDGE_ZONE_RATIO: float = 0.15
    REID_EMBEDDING_WEIGHT: float = 0.6
    REID_COLOR_WEIGHT: float = 0.25
    REID_SIZE_WEIGHT: float = 0.15
    REID_ACCEPT_THRESHOLD: float = 0.6
    REID_MIN_MARGIN: float = 0.12
    # Directional sequential handoff (cross-camera Re-ID, OCR-less)
    REID_DIRECTIONAL_HANDOFF_ENABLED: bool = True
    REID_DIRECTIONAL_MAX_TRANSIT_SEC: float = 20.0
    REID_DIRECTIONAL_MIN_TRANSIT_SEC: float = -3.0
    REID_DIRECTIONAL_MIN_VELOCITY_PX: float = 5.0
    REID_DIRECTIONAL_EDGE_ZONE_RATIO: float = 0.2
    REID_DIRECTIONAL_EMBEDDING_WEIGHT: float = 0.5
    REID_DIRECTIONAL_DIRECTION_WEIGHT: float = 0.3
    REID_DIRECTIONAL_TIME_WEIGHT: float = 0.2
    REID_DIRECTIONAL_ACCEPT_THRESHOLD: float = 0.6
    REID_DIRECTIONAL_EMBEDDING_FLOOR: float = 0.45
    REID_REVERSE_MOTION_GUARD_ENABLED: bool = True
    # Diversity ceiling for the per-identity embedding buffer. Embeddings are
    # extracted every frame; without this the 20 buffered vectors are the last
    # ~1-2s of near-identical poses. Skip an incoming vector whose cosine to the
    # last kept one is >= this, so the buffer spans distinct poses across the
    # track's life (better cross-camera "1 vs many" recall). 1.0 disables it.
    REID_EMBEDDING_DIVERSITY_MAX_COS: float = 0.98
    CLAHE_CLIP_LIMIT: float = 3.0
    CLAHE_TILE_SIZE: int = 8
    # Gray-world white balance before CLAHE (heaviest per-frame CPU step).
    # Toggle off to test whether YOLO still detects well without it.
    CLAHE_ENABLE_GRAY_WORLD: bool = True
    # Cân bằng sáng trên uint8 (~10× nhanh hơn bản float32, lệch trung bình ~1.3 mức).
    # Đặt false để quay lại đúng bản float32 cũ khi cần so sánh bitwise.
    CLAHE_FAST: bool = True
    # Tỉ lệ frame đưa vào CLAHE + detector. 1.0 = nguyên frame gốc (mặc định).
    # 0.5 = nhanh hơn nhiều nhưng box lệch nhẹ (đo được IoU min 0.963) → chỉ bật sau
    # khi chạy `make ab-detect` trên chính camera đó và thấy ĐẠT.
    DETECT_SCALE: float = 1.0
    # Nới crop OCR/embedding thêm tỉ lệ này khi DETECT_SCALE < 1.0 (bù box lệch vài px).
    CROP_PAD_RATIO: float = 0.05
    # Chạy CLAHE ở kích thước detector (letterbox nội dung trước, pad sau) thay vì ở
    # full-res rồi mới letterbox. Đặt false để quay lại đường cũ.
    CLAHE_AFTER_LETTERBOX: bool = True
    # Hệ số letterbox trước CLAHE. 1.0 = đúng imgsz (nhanh nhất nhưng MẤT box trên frame
    # cam6: mất 1 box conf 0.966). 1.5 = CLAHE ở 1440 rồi thu về 960: giữ đủ box, IoU min
    # 0.9858, vẫn nhanh hơn ~70% so với CLAHE full-res. Kẹp trong [1.0, 2.0].
    CLAHE_LETTERBOX_SCALE: float = 1.5
    FUSED_FRAME_MAX_WIDTH: int = 1280
    FUSED_FRAME_MAX_HEIGHT: int = 720
    PREVIEW_MAX_WIDTH: int = 1280
    PREVIEW_MAX_HEIGHT: int = 720

    # OCR / Paddle configuration
    OCR_INTERVAL_SEC: float = 0.5
    # Seconds final ship_id must stay unchanged before OCR/visual stop (0 = disabled).
    SHIP_ID_LOCK_STABLE_SEC: float = 60.0
    ENABLE_OCR: bool = True
    # Gate OCR/embedding ship_id on catalog (Qdrant/vessel DB). False = trust
    # rule-engine output (regex/blacklist/convert) even for unregistered ships.
    SHIP_ID_REQUIRE_CATALOG: bool = False
    OCR_LABEL_TTL_SEC: float = 5.0
    SAVE_MIN_INTERVAL_SEC: float = 20.0
    OCR_AUDIT_ENABLE: bool = True
    OCR_AUDIT_SAVE_FRAMES: bool = True
    OCR_CONFIDENCE_THRESHOLD: float = 0.0
    # PaddleOCR: dùng model cục bộ trong models/paddle_ocr/ thay vì tải về ~/.paddlex.
    # Rỗng = để PaddleX tự resolve/tải như cũ.
    PADDLE_OCR_DET_MODEL_DIR: str = "models/paddle_ocr/PP-OCRv6_medium_det"
    PADDLE_OCR_REC_MODEL_DIR: str = "models/paddle_ocr/PP-OCRv6_medium_rec"
    # TensorRT cho Paddle: Paddle tự build + cache engine con (run_mode=trt_fp16 hoặc
    # trt_fp32), KHÔNG sinh file .engine. Mặc định TẮT: Paddle 3.3.0 lỗi ở converter TRT
    # (paddle/tensorrt/impls/manipulation.py → stack_converter) khi convert model OCR,
    # bật lên sẽ tốn ~1-2 phút rồi mới lùi về fp32. Xem scripts/probe_paddle_trt.py.
    PADDLE_USE_TENSORRT: bool = False
    PADDLE_TRT_PRECISION: str = "fp16"
    
    # Video record configuration
    RECORD_ENABLE: bool = True
    RECORD_MAX_DURATION_MIN: int = 5
    RECORD_NO_BOAT_GAP_SEC: int = 20
    # Single FPS for RTSP read, AI, dashboard preview, and video record (port_configs: record_fps).
    RECORD_FPS: int = 20

    # RTSP decode — FFmpeg NVDEC (requires CUDA-enabled ffmpeg binary)
    RTSP_NVDEC_ENABLED: bool = False
    RTSP_NVDEC_HWACCEL: str = 'cuda'  # cuda | nvdec (auto-picks first available)
    FFMPEG_PATH: str = ''  # empty = PATH, then imageio-ffmpeg
    RTSP_TRANSPORT: str = 'tcp'  # tcp | udp
    # GStreamer NVDEC: nvh264dec/nvh265dec → cudaconvertscale(BGR,GPU) → cudadownload.
    # Requires gst-plugins-bad nvcodec with cudaconvertscale + libnvrtc.so in LD_LIBRARY_PATH.
    # Takes priority over FFmpeg NVDEC when both RTSP_NVDEC_ENABLED and this are True.
    RTSP_GST_NVDEC_ENABLED: bool = False

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
    VISUAL_MATCH_THRESHOLD: float = 0.55
    VISUAL_NO_OCR_MATCH_THRESHOLD: float = 0.55
    VISUAL_TOP_K: int = 20
    # Rỗng = tự tìm trong models/dinov2/: <backbone>.engine (TensorRT) → .safetensors (timm)
    VISUAL_MODEL_PATH: str = ""
    VISUAL_WEIGHTS_PATH: str = ""
    VISUAL_ENGINE_PATH: str = ""
    VISUAL_PREFER_ENGINE: bool = True
    VISUAL_ENGINE_MAX_BATCH: int = 8
    VISUAL_BACKBONE: str = "vit_base_patch14_dinov2"
    VISUAL_EMBEDDING_DIM: int = 768
    VISUAL_IMAGE_SIZE: int = 224
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
    QDRANT_COLLECTION: str = "vessel_visual_embeddings_dinov2"
    QDRANT_VECTOR_SIZE: int = 768
    QDRANT_DISTANCE: str = "COSINE"
    QDRANT_TIMEOUT_SEC: float = 15.0

    # Training snapshot collection (crops + snapshot/yolo full-frame labels for YOLO)
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

    # Zalo Bot (unknown ship identity notifications)
    ZALO_BOT_TOKEN: str = ''
    ZALO_CHAT_ID: str = ''
    # Bot cảnh báo nghiệp vụ riêng; chat ID phải thuộc bot này.
    ZALO_ALERT_BOT_TOKEN: str = ''
    ZALO_ALERT_CHAT_ID: str = ''
    ZALO_WEBHOOK_SECRET: str = ''
    ZALO_ENABLED: bool = False
    ZALO_PUBLIC_BASE_URL: str = ''
    # Webhook registration URL base (defaults to ZALO_PUBLIC_BASE_URL). Use when webhook is on a
    # Cloudflare Worker route while media/preview stays on ZALO_PUBLIC_BASE_URL.
    ZALO_WEBHOOK_BASE_URL: str = ''
    # Use long-polling when Cloudflare blocks Zalo webhook (User-Agent Java/1.8.0_192, error 1010)
    ZALO_POLLING_ENABLED: bool = False
    ZALO_MEDIA_TTL_HOURS: int = 168
    # Wait for detection image (+ video when expected) before sending Zalo notify
    ZALO_NOTIFY_MEDIA_WAIT_SEC: int = 180
    ZALO_NOTIFY_MEDIA_POLL_SEC: float = 3.0

    # Licensing (Keygate) — kiểm tra bản quyền định kỳ qua license.dtgsoft.vn
    LICENSE_SERVER_URL: str = 'https://license.dtgsoft.vn'
    # Key nhập từ trang quản trị; chỉ lưu DB dưới dạng đã mã hoá (xem utils/crypto.py).
    # Chỉ dùng để bootstrap MỘT LẦN khi DB chưa có key (dev/di trú); app mã hoá
    # vào DB rồi ops nên xoá biến này khỏi .env.
    LICENSE_KEY: str = ''
    # CHỈ dev: override "mã máy" (identifier) gửi Keygate. Production để trống —
    # mã máy thật tính từ hardware fingerprint (/etc/machine-id + DMI,
    # xem app/core/license/machine.py và scripts/install_license_identity.sh).
    LICENSE_INSTANCE_ID: str = ''
    # off = tắt kiểm tra, warn = chỉ cảnh báo, enforce = chặn khi hết hạn.
    LICENSE_ENFORCEMENT: Literal['off', 'warn', 'enforce'] = 'warn'
    # Chu kỳ gọi check-in lên license server (giờ).
    LICENSE_CHECKIN_HOURS: int = 6
    # Timeout HTTP khi gọi license server (giây).
    LICENSE_HTTP_TIMEOUT_SEC: float = 5.0

    # Logging
    LOG_LEVEL: Literal['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG'] = 'INFO'
    # Ghi log ra file để trang "Xem Logs" tail được. Rotating theo dung lượng.
    LOG_TO_FILE: bool = True
    LOG_FILE_PATH: str = 'logs/app.log'
    LOG_FILE_MAX_BYTES: int = 10 * 1024 * 1024  # 10MB/file
    LOG_FILE_BACKUP_COUNT: int = 5

    model_config = SettingsConfigDict(
        env_file='.env',
        extra='ignore',
    )

settings = Settings()
