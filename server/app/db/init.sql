-- =============================================================================
-- Bason Port Management System — Database Initialization
-- Generated from: comprehensive_port_erd_98057811.plan.md
-- Tables: 15 | Relationships: 19
-- =============================================================================

-- Enable pgcrypto for UUID support if needed later
-- CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- =============================================================================
-- 1. LOOKUP / REFERENCE TABLES (no FK dependencies)
-- =============================================================================

CREATE TABLE IF NOT EXISTS roles (
    id          SERIAL PRIMARY KEY,
    role_name   VARCHAR(50) UNIQUE NOT NULL,
    description TEXT,
    permissions JSONB
);

CREATE TABLE IF NOT EXISTS vessel_types (
    id          SERIAL PRIMARY KEY,
    type_name   VARCHAR(50) UNIQUE NOT NULL,
    description TEXT,
    created_at  TIMESTAMP DEFAULT NOW()
);

-- =============================================================================
-- 2. CORE ENTITY TABLES
-- =============================================================================

CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    username        VARCHAR(50) UNIQUE NOT NULL,
    hashed_password VARCHAR(255),
    email           VARCHAR(100) UNIQUE,
    full_name       VARCHAR(100),
    phone           VARCHAR(20),
    role_id         INTEGER REFERENCES roles(id) ON DELETE SET NULL,
    is_active       BOOLEAN DEFAULT TRUE,
    last_login      TIMESTAMP,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS vessels (
    id                  SERIAL PRIMARY KEY,
    ship_id             VARCHAR(50) UNIQUE NOT NULL,
    name                VARCHAR(100),
    vessel_type_id      INTEGER REFERENCES vessel_types(id) ON DELETE SET NULL,
    owner               VARCHAR(200),
    registration_number VARCHAR(100),
    is_active           BOOLEAN DEFAULT TRUE,
    last_seen           TIMESTAMP,
    created_at          TIMESTAMP DEFAULT NOW(),
    updated_at          TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS fee_configs (
    id              SERIAL PRIMARY KEY,
    vessel_type_id  INTEGER REFERENCES vessel_types(id) ON DELETE SET NULL,
    fee_name        VARCHAR(100) NOT NULL,
    base_fee        DECIMAL(12, 2) NOT NULL,
    unit            VARCHAR(20),
    is_active       BOOLEAN DEFAULT TRUE,
    effective_from  DATE,
    effective_to    DATE,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

-- =============================================================================
-- 3. ACTIVITY TABLES (depend on vessels / users)
-- =============================================================================

CREATE TABLE IF NOT EXISTS detections (
    id                SERIAL PRIMARY KEY,
    vessel_id         INTEGER REFERENCES vessels(id) ON DELETE SET NULL,
    track_id          VARCHAR(100) UNIQUE,
    start_time        TIMESTAMP,
    end_time          TIMESTAMP,
    video_path        TEXT,
    audit_image_path  TEXT,
    ocr_results       JSONB,
    confidence        FLOAT,
    is_accepted       BOOLEAN,
    verified_by       INTEGER REFERENCES users(id) ON DELETE SET NULL,
    verified_at       TIMESTAMP,
    rejection_reason  TEXT,
    created_at        TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS orders (
    id           SERIAL PRIMARY KEY,
    order_number VARCHAR(50) UNIQUE NOT NULL,
    vessel_id    INTEGER REFERENCES vessels(id) ON DELETE SET NULL,
    description  TEXT,
    total_amount DECIMAL(12, 2),
    status       VARCHAR(20) DEFAULT 'PENDING',
    notes        TEXT,
    created_by   INTEGER REFERENCES users(id) ON DELETE SET NULL,
    updated_by   INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at   TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,
    updated_at   TIMESTAMP DEFAULT NOW(),
    CONSTRAINT chk_orders_status CHECK (status IN ('PENDING', 'COMPLETED', 'CANCELLED'))
);

-- =============================================================================
-- 4. FINANCIAL TABLES
-- =============================================================================

CREATE TABLE IF NOT EXISTS invoices (
    id              SERIAL PRIMARY KEY,
    invoice_number  VARCHAR(50) UNIQUE NOT NULL,
    order_id        INTEGER REFERENCES orders(id) ON DELETE SET NULL,
    vessel_id       INTEGER REFERENCES vessels(id) ON DELETE SET NULL,
    detection_id    INTEGER REFERENCES detections(id) ON DELETE SET NULL,
    subtotal        DECIMAL(12, 2),
    tax_amount      DECIMAL(12, 2),
    total_amount    DECIMAL(12, 2) NOT NULL,
    payment_status  VARCHAR(20) DEFAULT 'UNPAID',
    due_date        DATE,
    paid_at         TIMESTAMP,
    deleted_at      TIMESTAMPTZ,
    notes           TEXT,
    creation_source VARCHAR(20) NOT NULL DEFAULT 'USER',
    created_by      INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW(),
    CONSTRAINT chk_invoices_payment_status CHECK (payment_status IN ('UNPAID', 'PARTIAL', 'PAID', 'OVERDUE', 'CANCELLED')),
    CONSTRAINT chk_invoices_creation_source CHECK (creation_source IN ('USER', 'ORDER_AUTO', 'AI'))
);

CREATE TABLE IF NOT EXISTS invoice_items (
    id             SERIAL PRIMARY KEY,
    invoice_id     INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    fee_config_id  INTEGER REFERENCES fee_configs(id) ON DELETE SET NULL,
    description    VARCHAR(200),
    quantity       DECIMAL(10, 2),
    unit_price     DECIMAL(12, 2) NOT NULL,
    amount         DECIMAL(12, 2) NOT NULL
);

CREATE TABLE IF NOT EXISTS payments (
    id                SERIAL PRIMARY KEY,
    invoice_id        INTEGER NOT NULL REFERENCES invoices(id) ON DELETE RESTRICT,
    amount            DECIMAL(12, 2) NOT NULL,
    payment_method    VARCHAR(50),
    payment_reference VARCHAR(100),
    paid_at           TIMESTAMP NOT NULL DEFAULT NOW(),
    notes             TEXT,
    created_by        INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at        TIMESTAMP DEFAULT NOW()
);

-- =============================================================================
-- 5. DETECTION SUPPORT TABLES
-- =============================================================================

CREATE TABLE IF NOT EXISTS detection_media (
    id           SERIAL PRIMARY KEY,
    detection_id INTEGER NOT NULL REFERENCES detections(id) ON DELETE CASCADE,
    media_type   VARCHAR(20) NOT NULL,
    file_path    TEXT NOT NULL,
    file_size    BIGINT,
    created_at   TIMESTAMP DEFAULT NOW(),
    CONSTRAINT chk_detection_media_type CHECK (media_type IN ('image', 'video', 'thumbnail'))
);

-- =============================================================================
-- 6. CONFIG & LOG TABLES
-- =============================================================================

CREATE TABLE IF NOT EXISTS port_configs (
    id          SERIAL PRIMARY KEY,
    key         VARCHAR(100) UNIQUE NOT NULL,
    value       TEXT NOT NULL,
    description TEXT,
    updated_by  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    updated_at  TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cameras (
    id          SERIAL PRIMARY KEY,
    camera_name VARCHAR(100) NOT NULL,
    rtsp_url    TEXT UNIQUE NOT NULL,
    is_active   BOOLEAN DEFAULT TRUE,
    location    VARCHAR(200),
    description TEXT,
    created_at  TIMESTAMP DEFAULT NOW(),
    updated_at  TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS port_logs (
    id             SERIAL PRIMARY KEY,
    seq            INTEGER,
    ships_completed_today INTEGER,
    logged_at      TIMESTAMP DEFAULT NOW(),
    track_id       VARCHAR(100),
    voted_ship_id  VARCHAR(50),
    first_seen_at  TIMESTAMP,
    last_seen_at   TIMESTAMP,
    confidence     FLOAT,
    ocr_attempts   INTEGER,
    vote_summary   JSONB,
    schema_version INTEGER DEFAULT 3
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    action      VARCHAR(50) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    entity_id   INTEGER,
    details     JSONB,
    ip_address  VARCHAR(45),
    created_at  TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS export_logs (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    export_type VARCHAR(50) NOT NULL,
    file_path   TEXT,
    filters     JSONB,
    row_count   INTEGER,
    created_at  TIMESTAMP DEFAULT NOW()
);

-- =============================================================================
-- INDEXES — frequently queried fields
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_vessels_ship_id        ON vessels(ship_id);
CREATE INDEX IF NOT EXISTS idx_vessels_vessel_type_id ON vessels(vessel_type_id);
CREATE INDEX IF NOT EXISTS idx_detections_vessel_id   ON detections(vessel_id);
CREATE INDEX IF NOT EXISTS idx_detections_track_id    ON detections(track_id);
CREATE INDEX IF NOT EXISTS idx_detections_created_at  ON detections(created_at);
CREATE INDEX IF NOT EXISTS idx_orders_vessel_id       ON orders(vessel_id);
CREATE INDEX IF NOT EXISTS idx_orders_status          ON orders(status);
CREATE INDEX IF NOT EXISTS idx_invoices_order_id      ON invoices(order_id);
CREATE INDEX IF NOT EXISTS idx_invoices_vessel_id     ON invoices(vessel_id);
CREATE INDEX IF NOT EXISTS idx_invoices_payment_status ON invoices(payment_status);
CREATE INDEX IF NOT EXISTS idx_port_logs_logged_at    ON port_logs(logged_at);
CREATE INDEX IF NOT EXISTS idx_port_logs_track_id     ON port_logs(track_id);
CREATE INDEX IF NOT EXISTS idx_cameras_is_active       ON cameras(is_active);
CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id     ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_entity      ON audit_logs(entity_type, entity_id);

-- =============================================================================
-- SEED DATA — minimum required for system startup
-- =============================================================================

INSERT INTO roles (role_name, description, permissions) VALUES
    ('admin',    'Full system access',     '{"all": true}'::jsonb),
    ('operator', 'Port operations staff',  '{"detections": true, "orders": true, "vessels": true}'::jsonb),
    ('viewer',   'Read-only access',       '{"read": true}'::jsonb)
ON CONFLICT (role_name) DO NOTHING;

INSERT INTO vessel_types (type_name, description) VALUES
    ('Cargo',    'General cargo vessels'),
    ('Tanker',   'Oil and chemical tankers'),
    ('Fishing',  'Commercial fishing boats'),
    ('Passenger','Passenger ferries and cruise ships'),
    ('Other',    'Miscellaneous vessel types')
ON CONFLICT (type_name) DO NOTHING;

INSERT INTO port_configs (key, value, description) VALUES
    ('port_name',           'Bason Port',   'Display name of the port'),
    ('detection_confidence_threshold', '0.6', 'Minimum OCR confidence to auto-accept'),
    ('invoice_tax_rate',    '0.1',          'Default tax rate (10%)'),
    ('invoice_due_days',    '30',           'Days until invoice is overdue'),
    ('model_path',          'app/yolo11n.pt', 'Path to YOLO model file'),
    ('device',              '0',            'Inference device (0 for GPU, cpu for CPU)'),
    ('conf',                '0.75',         'YOLO detection confidence threshold'),
    ('resize_scale',        '0.5',          'Frame resize scale for processing'),
    ('track_min_hits',      '30',           'Minimum hits to confirm a track'),
    ('track_max_tentative_misses', '10',    'Max misses for tentative tracks'),
    ('track_max_lost_frames', '80',         'Max frames to keep a lost track'),
    ('track_iou_threshold', '0.3',          'IoU threshold for tracking'),
    ('track_reid_window_sec', '120',        'Re-ID time window in seconds'),
    ('track_reid_max_dist', '150',          'Max distance for spatial Re-ID'),
    ('ocr_interval_frames', '10',           'Frames between OCR attempts'),
    ('enable_ocr',          'true',         'Enable/Disable OCR globally'),
    ('ocr_label_ttl_sec',   '5.0',          'Time to display OCR label on UI'),
    ('save_min_interval_sec', '20',         'Min interval between saving detection images'),
    ('ocr_audit_enable',    'true',         'Enable OCR audit logging'),
    ('ocr_audit_save_frames', 'true',       'Save full frames for OCR audit'),
    ('record_enable',       'true',         'Enable video recording of detections'),
    ('record_max_duration_min', '5',        'Max recording duration in minutes'),
    ('record_no_boat_gap_sec', '20',        'Gap in seconds to stop recording after boat leaves'),
    ('record_fps',          '20',           'FPS for recorded video')
ON CONFLICT (key) DO NOTHING;

INSERT INTO cameras (camera_name, rtsp_url, location) VALUES
    ('Cảng trước', 'rtsp://admin:thuongnhat.123@@bentaubason0326.cameraddns.net:1554/Streaming/Channels/701', 'Camera phía trước'),
    ('Cảng sau',   'rtsp://admin:thuongnhat.123@@bentaubason0326.cameraddns.net:1554/Streaming/Channels/601', 'Camera phía sau')
ON CONFLICT (rtsp_url) DO NOTHING;
