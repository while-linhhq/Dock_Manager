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
        ('resize_scale',                   '0.5',        'Frame resize scale for processing'),
        ('track_min_hits',                 '30',         'Minimum hits to confirm a track'),
        ('track_max_tentative_misses',     '10',         'Max misses for tentative tracks'),
        ('track_max_lost_frames',          '80',         'Max frames to keep a lost track'),
        ('track_iou_threshold',            '0.3',        'IoU threshold for tracking'),
        ('track_reid_window_sec',          '120',        'Re-ID time window in seconds'),
        ('track_reid_max_dist',            '150',        'Max distance for spatial Re-ID'),
        ('ocr_interval_frames',            '10',         'Frames between OCR attempts'),
        ('enable_ocr',                     'true',       'Enable/Disable OCR globally'),
        ('ocr_label_ttl_sec',              '5.0',        'Time to display OCR label on UI'),
        ('save_min_interval_sec',          '20',         'Min interval between saving detection images'),
        ('ocr_audit_enable',               'true',       'Enable OCR audit logging'),
        ('ocr_audit_save_frames',          'true',       'Save full frames for OCR audit'),
        ('record_enable',                  'true',       'Enable video recording of detections'),
        ('record_max_duration_min',        '5',          'Max recording duration in minutes'),
        ('record_no_boat_gap_sec',         '20',         'Gap in seconds to stop recording after boat leaves'),
        ('record_fps',                     '20',         'FPS for recorded video')
    ON CONFLICT (key) DO NOTHING;
    """
    with engine.connect() as conn:
        conn.execute(text(seed_sql))
        conn.commit()
    logger.info('Seed data inserted.')


if __name__ == '__main__':
    init_db()
