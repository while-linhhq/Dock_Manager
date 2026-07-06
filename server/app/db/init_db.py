"""
Run this script once to initialize the database schema.

Usage (from server/ directory, with conda demo_core active):
    python -m app.db.init_db

Or via SQL directly (recommended for production):
    psql -U <user> -d <database> -f app/db/init.sql
"""
import os
import logging
from pathlib import Path

from sqlalchemy import text
from app.db.session import engine, Base
from app.db.schema_patches import apply_schema_patches

# Import all models so Base.metadata picks them up
import app.models  # noqa: F401

logger = logging.getLogger(__name__)


def create_tables_via_orm() -> None:
    """Create all tables using SQLAlchemy metadata (no FK ordering issues)."""
    Base.metadata.create_all(bind=engine)
    logger.info('All tables created via ORM.')


def run_init_sql() -> None:
    """Execute init.sql — includes indexes and seed data."""
    sql_path = Path(__file__).parent / 'init.sql'
    if not sql_path.exists():
        logger.warning('init.sql not found, skipping.')
        return

    sql = sql_path.read_text(encoding='utf-8')
    with engine.connect() as conn:
        conn.execute(text(sql))
        conn.commit()
    logger.info('init.sql executed successfully.')


def init_db() -> None:
    """
    Full database initialization:
    1. Create tables via SQLAlchemy ORM (handles FK ordering automatically)
    2. Run init.sql for indexes + seed data (ON CONFLICT DO NOTHING — idempotent)
    """
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    logger.info('Initializing database...')

    create_tables_via_orm()
    apply_schema_patches()

    # Seed data and indexes via SQL file
    run_init_sql()

    logger.info('Database initialization complete.')


def _run_seed_data() -> None:
    """Insert seed data (idempotent — uses ON CONFLICT DO NOTHING)."""
    from sqlalchemy import text

    seed_sql = """
    INSERT INTO roles (role_name, description, permissions) VALUES
        ('admin',    'Full system access',     '{"all": true}'),
        ('operator', 'Port operations staff',  '{"menus": ["dashboard", "orders", "revenue", "vessels", "port", "stats", "backup", "profile"]}'),
        ('viewer',   'Read-only access',       '{"menus": ["dashboard", "stats", "backup", "profile"]}')
    ON CONFLICT (role_name) DO NOTHING;

    INSERT INTO vessel_types (type_name, description) VALUES
        ('Cargo',     'General cargo vessels'),
        ('Tanker',    'Oil and chemical tankers'),
        ('Fishing',   'Commercial fishing boats'),
        ('Passenger', 'Passenger ferries and cruise ships'),
        ('Other',     'Miscellaneous vessel types')
    ON CONFLICT (type_name) DO NOTHING;

    INSERT INTO port_configs (key, value, description) VALUES
        ('port_name',                      'Bason Port', 'Display name of the port'),
        ('detection_confidence_threshold', '0.6',        'Minimum OCR confidence to auto-accept'),
        ('invoice_tax_rate',               '0.1',        'Default tax rate (10%)'),
        ('invoice_due_days',               '30',         'Days until invoice is overdue'),
        ('model_path',                     'app/yolo11n.pt', 'Path to YOLO model file'),
        ('device',                         '0',          'Inference device (0 for GPU, cpu for CPU)'),
        ('conf',                           '0.75',       'YOLO detection confidence threshold'),
        ('yolo_imgsz',                     '640',        'YOLO inference input size (letterbox, e.g. 640 or 960)'),
        ('resize_scale',                   '0.5',        'Frame resize scale for processing'),
        ('track_iou_threshold',            '0.3',        'IoU threshold for tracking'),
        ('track_dedup_iomin_threshold',    '0.0',        'Loc bbox trung cung 1 track: bo box conf thap khi IoMin (giao/dien tich box nho) >= nguong. 0 = tat.'),
        ('track_reid_window_sec',          '120',        'Re-ID time window in seconds'),
        ('track_reid_max_dist',            '150',        'Max distance for spatial Re-ID'),
        ('track_min_confirm_sec',          '1.5',        'Seconds before TENTATIVE becomes CONFIRMED'),
        ('track_max_tentative_sec',        '0.5',        'Seconds without match before tentative track is removed'),
        ('track_max_lost_sec',             '4.0',        'Seconds in LOST before track is removed'),
        ('ocr_interval_sec',               '0.5',        'Seconds between OCR attempts'),
        ('enable_ocr',                     'true',       'Enable/Disable OCR globally'),
        ('ocr_label_ttl_sec',              '5.0',        'Time to display OCR label on UI'),
        ('save_min_interval_sec',          '20',         'Min interval between saving detection images'),
        ('ocr_audit_enable',               'true',       'Enable OCR audit logging'),
        ('ocr_audit_save_frames',          'true',       'Save full frames for OCR audit'),
        ('record_enable',                  'true',       'Enable video recording of detections'),
        ('record_max_duration_min',        '5',          'Max recording duration in minutes'),
        ('record_no_boat_gap_sec',         '20',         'Gap in seconds to stop recording after boat leaves'),
        ('record_fps',                     '20',         'Global pipeline FPS (RTSP, AI, preview, video record)'),
        ('rtsp_nvdec_enabled',             'false',      'Hardware-decode RTSP via FFmpeg NVDEC'),
        ('ffmpeg_path',                    '',           'Path to CUDA-enabled ffmpeg (empty = auto)'),
        ('rtsp_transport',                 'tcp',        'RTSP transport: tcp or udp'),
        ('sync_tolerance_ms',              '1200',       'Max timestamp spread (ms) for multi-camera frame sync'),
        ('sync_camera_offsets_ms',         '',           'Per-camera latency offsets for frame sync, JSON map or comma list'),
        ('seam_anchor_enabled',            'true',       'Bật seam anchor giữ ID khi tàu neo chia 2 camera'),
        ('seam_roi_width_ratio',           '0.15',       'Tỉ lệ bề rộng vùng seam (theo width của camera kề)'),
        ('seam_proximity_px',              '40',         'Khoảng cách (px) từ bbox tới cạnh để được anchor'),
        ('bg_subtract_threshold',          '0.18',       'Ngưỡng tỉ lệ foreground để coi seam là OCCUPIED'),
        ('bg_model_history',               '500',        'history của MOG2 background model'),
        ('bg_var_threshold',               '25',         'varThreshold của MOG2'),
        ('bg_min_seed_frames',             '100',        'Số frame seed trước khi bg model sẵn sàng'),
        ('anchor_iou_resurrect_threshold', '0.3',        'IoU tối thiểu để resurrect anchor khi YOLO detect lại'),
        ('anchor_embedding_match_enabled', 'true',       'Bật so khớp embedding khi re-validate / resurrect'),
        ('anchor_embedding_sim_threshold', '0.65',       'Cosine similarity tối thiểu cho embedding match'),
        ('anchor_revalidation_sec',        '5.0',        'Chu kỳ re-validate appearance (giây)'),
        ('anchor_departed_grace_sec',      '30.0',       'Thời gian chờ trước khi coi tàu đã rời (giây)'),
        ('anchor_max_duration_sec',        '172800',     'Tối đa giữ anchor (giây) để tránh kẹt vô hạn'),
        ('anchor_db_update_debounce_sec',  '30.0',       'Debounce ghi last_seen vào DB cho anchor (giây)'),
        ('anchor_min_stationary_sec',        '8.0',        'Thời gian tàu STATIC tối thiểu trước khi được anchor'),
        ('anchor_color_hsv_tolerance_h',   '15',         'Dung sai Hue (độ) khi so màu re-validate anchor'),
        ('reid_overlap_merge_enabled',     'true',       'Bật merge khi tàu thấy đồng thời trên 2 camera kề (overlap FOV)'),
        ('reid_edge_zone_ratio',           '0.15',       'Bề rộng vùng overlap (tỉ lệ width) để xét merge cross-camera'),
        ('reid_embedding_weight',          '0.6',        'Trọng số embedding trong fusion score merge'),
        ('reid_color_weight',              '0.25',       'Trọng số HSV similarity trong fusion score merge'),
        ('reid_size_weight',               '0.15',       'Trọng số tỉ lệ kích thước box trong fusion score merge'),
        ('reid_accept_threshold',          '0.6',        'Ngưỡng tổng score mềm để chấp nhận merge'),
        ('reid_min_margin',                '0.12',       'Chênh score tối thiểu so với candidate #2 (chống nhầm)'),
        ('reid_directional_handoff_enabled', 'true',      'Bật handoff tuần tự khi tàu rời cam này sang cam kề (không cần OCR)'),
        ('reid_directional_max_transit_sec', '20',        'Thời gian tối đa (giây) tàu di chuyển giữa 2 cam kề để coi là handoff hợp lệ'),
        ('reid_directional_min_transit_sec', '-3',        'Dung sai âm (giây): xuất hiện sớm hơn = concurrent (để overlap merge xử lý)'),
        ('reid_directional_min_velocity_px', '5',         'Vận tốc ngang tối thiểu (px/giây) để xác định hướng di chuyển rõ ràng'),
        ('reid_directional_edge_zone_ratio', '0.2',       'Bề rộng vùng biên (tỉ lệ width) tàu phải xuất hiện ở cam nhận'),
        ('reid_directional_embedding_weight','0.5',       'Trọng số embedding trong score handoff hướng'),
        ('reid_directional_direction_weight','0.3',       'Trọng số khớp hướng di chuyển trong score handoff'),
        ('reid_directional_time_weight',   '0.2',        'Trọng số hợp lý thời gian trong score handoff'),
        ('reid_directional_accept_threshold','0.6',       'Ngưỡng tổng score để chấp nhận handoff hướng'),
        ('reid_directional_embedding_floor','0.45',       'Sàn embedding cosine: dưới ngưỡng này không merge dù hướng/thời gian khớp'),
        ('reid_reverse_motion_guard_enabled','true',      'Chặn tạo IN giả khi tàu lùi ra chạm lại vùng cam trước (đã có OUT)'),
        ('reid_embedding_diversity_max_cos','0.98',       'Trần đa dạng buffer embedding: bỏ vector có cosine >= mức này so với vector kề trước (0.98). 1.0 = tắt'),
        ('sepay_api_token',                '',           'Bearer token API giao dịch từ my.sepay.vn'),
        ('sepay_sync_interval_sec',        '30',         'Chu kỳ đồng bộ SEPay (giây)'),
        ('sepay_cron_secret',              '',           'Secret cho cron gọi POST /api/v1/sepay/sync/cron'),
        ('sepay_bank_account',             '',           'Số tài khoản nhận chuyển khoản (hiển thị QR)'),
        ('sepay_bank_name',                '',           'Tên ngân hàng (VD: Vietcombank, BIDV)'),
        ('sepay_account_name',             '',           'Tên chủ tài khoản'),
        ('autostart_group_id',             '',           'ID camera group tự chạy khi backend khởi động (rỗng = group active id lớn nhất)')
    ON CONFLICT (key) DO NOTHING;
    """
    with engine.connect() as conn:
        conn.execute(text(seed_sql))
        conn.commit()
    logger.info('Seed data inserted.')


if __name__ == '__main__':
    init_db()
