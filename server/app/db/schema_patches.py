"""
Idempotent schema adjustments for existing databases (ORM create_all does not ALTER).

Keeps dev/prod DBs aligned when new columns are added to models before formal migrations.
"""

import logging

from sqlalchemy import inspect, text

from app.db.session import engine

logger = logging.getLogger(__name__)

_patch_quiet = False
_patch_applied: list[str] = []


def _patch_done(label: str) -> None:
    """Record a schema change; log only when not in quiet startup mode."""
    _patch_applied.append(label)
    if not _patch_quiet:
        logger.info('schema_patches: %s', label)


def _ensure_invoices_deleted_at() -> None:
    try:
        inspector = inspect(engine)
        if not inspector.has_table('invoices'):
            return
        cols = {c['name'] for c in inspector.get_columns('invoices')}
        if 'deleted_at' in cols:
            return
    except Exception as err:
        logger.warning('schema_patches: could not inspect invoices table: %s', err)
        return

    dialect = engine.dialect.name
    stmt = None
    if dialect == 'postgresql':
        stmt = text('ALTER TABLE invoices ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ')
    elif dialect == 'sqlite':
        stmt = text('ALTER TABLE invoices ADD COLUMN deleted_at TIMESTAMP')
    else:
        logger.warning(
            'schema_patches: unknown dialect %s — add invoices.deleted_at manually',
            dialect,
        )
        return

    try:
        with engine.begin() as conn:
            conn.execute(stmt)
        _patch_done('added invoices.deleted_at')
    except Exception as err:
        logger.error('schema_patches: failed to add invoices.deleted_at: %s', err)
        raise


def _ensure_port_logs_ships_completed_today() -> None:
    try:
        inspector = inspect(engine)
        if not inspector.has_table('port_logs'):
            return
        cols = {c['name'] for c in inspector.get_columns('port_logs')}
        if 'ships_completed_today' in cols:
            return
    except Exception as err:
        logger.warning('schema_patches: could not inspect port_logs table: %s', err)
        return

    dialect = engine.dialect.name
    stmt = None
    if dialect == 'postgresql':
        stmt = text(
            'ALTER TABLE port_logs ADD COLUMN IF NOT EXISTS ships_completed_today INTEGER'
        )
    elif dialect == 'sqlite':
        stmt = text('ALTER TABLE port_logs ADD COLUMN ships_completed_today INTEGER')
    else:
        logger.warning(
            'schema_patches: unknown dialect %s — add port_logs.ships_completed_today manually',
            dialect,
        )
        return

    try:
        with engine.begin() as conn:
            conn.execute(stmt)
        _patch_done('added port_logs.ships_completed_today')
    except Exception as err:
        logger.error('schema_patches: failed to add port_logs.ships_completed_today: %s', err)
        raise


def _ensure_orders_total_amount() -> None:
    try:
        inspector = inspect(engine)
        if not inspector.has_table('orders'):
            return
        cols = {c['name'] for c in inspector.get_columns('orders')}
        if 'total_amount' in cols:
            return
    except Exception as err:
        logger.warning('schema_patches: could not inspect orders table: %s', err)
        return

    dialect = engine.dialect.name
    stmt = None
    if dialect == 'postgresql':
        stmt = text('ALTER TABLE orders ADD COLUMN IF NOT EXISTS total_amount DECIMAL(12, 2)')
    elif dialect == 'sqlite':
        stmt = text('ALTER TABLE orders ADD COLUMN total_amount NUMERIC(12, 2)')
    else:
        logger.warning(
            'schema_patches: unknown dialect %s — add orders.total_amount manually',
            dialect,
        )
        return

    try:
        with engine.begin() as conn:
            conn.execute(stmt)
        _patch_done('added orders.total_amount')
    except Exception as err:
        logger.error('schema_patches: failed to add orders.total_amount: %s', err)
        raise


def _ensure_invoices_creation_source() -> None:
    try:
        inspector = inspect(engine)
        if not inspector.has_table('invoices'):
            return
        cols = {c['name'] for c in inspector.get_columns('invoices')}
        if 'creation_source' in cols:
            return
    except Exception as err:
        logger.warning('schema_patches: could not inspect invoices table: %s', err)
        return

    dialect = engine.dialect.name
    stmt = None
    if dialect == 'postgresql':
        stmt = text(
            "ALTER TABLE invoices ADD COLUMN IF NOT EXISTS creation_source VARCHAR(20) NOT NULL DEFAULT 'USER'"
        )
    elif dialect == 'sqlite':
        stmt = text("ALTER TABLE invoices ADD COLUMN creation_source VARCHAR(20) NOT NULL DEFAULT 'USER'")
    else:
        logger.warning(
            'schema_patches: unknown dialect %s — add invoices.creation_source manually',
            dialect,
        )
        return

    try:
        with engine.begin() as conn:
            conn.execute(stmt)
        _patch_done('added invoices.creation_source')
    except Exception as err:
        logger.error('schema_patches: failed to add invoices.creation_source: %s', err)
        raise


def _ensure_detections_audit_image_path() -> None:
    try:
        inspector = inspect(engine)
        if not inspector.has_table('detections'):
            return
        cols = {c['name'] for c in inspector.get_columns('detections')}
        if 'audit_image_path' in cols:
            return
    except Exception as err:
        logger.warning('schema_patches: could not inspect detections table: %s', err)
        return

    dialect = engine.dialect.name
    stmt = None
    if dialect == 'postgresql':
        stmt = text('ALTER TABLE detections ADD COLUMN IF NOT EXISTS audit_image_path TEXT')
    elif dialect == 'sqlite':
        stmt = text('ALTER TABLE detections ADD COLUMN audit_image_path TEXT')
    else:
        logger.warning(
            'schema_patches: unknown dialect %s — add detections.audit_image_path manually',
            dialect,
        )
        return

    try:
        with engine.begin() as conn:
            conn.execute(stmt)
        _patch_done('added detections.audit_image_path')
    except Exception as err:
        logger.error('schema_patches: failed to add detections.audit_image_path: %s', err)
        raise


def _ensure_camera_groups() -> None:
    try:
        inspector = inspect(engine)
        if inspector.has_table('camera_groups') and inspector.has_table('camera_group_members'):
            return
    except Exception as err:
        logger.warning('schema_patches: could not inspect camera_groups tables: %s', err)
        return

    dialect = engine.dialect.name
    if dialect != 'postgresql':
        logger.warning(
            'schema_patches: unknown dialect %s — create camera_groups tables manually',
            dialect,
        )
        return

    stmts = [
        text(
            """
            CREATE TABLE IF NOT EXISTS camera_groups (
                id SERIAL PRIMARY KEY,
                name VARCHAR(120) UNIQUE NOT NULL,
                description TEXT,
                fusion_mode VARCHAR(20) NOT NULL DEFAULT 'layout',
                pipeline_mode VARCHAR(20) NOT NULL DEFAULT 'hybrid',
                canvas_width INTEGER NOT NULL DEFAULT 1920,
                canvas_height INTEGER NOT NULL DEFAULT 1080,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                CONSTRAINT chk_camera_groups_fusion_mode
                    CHECK (fusion_mode IN ('layout')),
                CONSTRAINT chk_camera_groups_pipeline_mode
                    CHECK (pipeline_mode IN ('hybrid', 'fused'))
            )
            """
        ),
        text(
            """
            CREATE TABLE IF NOT EXISTS camera_group_members (
                id SERIAL PRIMARY KEY,
                group_id INTEGER NOT NULL REFERENCES camera_groups(id) ON DELETE CASCADE,
                camera_id INTEGER NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
                role VARCHAR(20) NOT NULL DEFAULT 'tile',
                priority INTEGER NOT NULL DEFAULT 0,
                layout_x INTEGER NOT NULL DEFAULT 0,
                layout_y INTEGER NOT NULL DEFAULT 0,
                layout_w INTEGER,
                layout_h INTEGER,
                layout_rotation REAL NOT NULL DEFAULT 0,
                crop_top INTEGER NOT NULL DEFAULT 0,
                crop_bottom INTEGER NOT NULL DEFAULT 0,
                crop_left INTEGER NOT NULL DEFAULT 0,
                crop_right INTEGER NOT NULL DEFAULT 0,
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(group_id, camera_id),
                CONSTRAINT chk_camera_group_members_role
                    CHECK (role IN ('base', 'overlay', 'tile'))
            )
            """
        ),
        text(
            'CREATE INDEX IF NOT EXISTS ix_camera_group_members_group '
            'ON camera_group_members(group_id)'
        ),
        text(
            'CREATE INDEX IF NOT EXISTS ix_camera_group_members_camera '
            'ON camera_group_members(camera_id)'
        ),
    ]

    try:
        with engine.begin() as conn:
            for stmt in stmts:
                conn.execute(stmt)
        _patch_done('ensured camera_groups tables')
    except Exception as err:
        logger.error('schema_patches: failed to ensure camera_groups tables: %s', err)
        raise


def _ensure_camera_groups_layout_pipeline() -> None:
    try:
        inspector = inspect(engine)
        if not inspector.has_table('camera_groups'):
            return
        group_cols = {c['name'] for c in inspector.get_columns('camera_groups')}
        member_cols = (
            {c['name'] for c in inspector.get_columns('camera_group_members')}
            if inspector.has_table('camera_group_members')
            else set()
        )
    except Exception as err:
        logger.warning('schema_patches: could not inspect camera_groups table: %s', err)
        return

    dialect = engine.dialect.name
    if dialect == 'postgresql':
        stmts = [
            text("ALTER TABLE camera_groups ADD COLUMN IF NOT EXISTS pipeline_mode VARCHAR(20) NOT NULL DEFAULT 'hybrid'"),
            text("UPDATE camera_groups SET fusion_mode = 'layout' WHERE fusion_mode <> 'layout'"),
            text('ALTER TABLE camera_groups DROP CONSTRAINT IF EXISTS chk_camera_groups_fusion_mode'),
            text(
                """
                ALTER TABLE camera_groups
                ADD CONSTRAINT chk_camera_groups_fusion_mode
                CHECK (fusion_mode IN ('layout'))
                """
            ),
            text('ALTER TABLE camera_groups DROP CONSTRAINT IF EXISTS chk_camera_groups_pipeline_mode'),
            text(
                """
                ALTER TABLE camera_groups
                ADD CONSTRAINT chk_camera_groups_pipeline_mode
                CHECK (pipeline_mode IN ('hybrid', 'fused'))
                """
            ),
        ]
        if 'stitch_metadata' in group_cols:
            stmts.append(text('ALTER TABLE camera_groups DROP COLUMN IF EXISTS stitch_metadata'))
        if 'homography' in member_cols:
            stmts.append(text('ALTER TABLE camera_group_members DROP COLUMN IF EXISTS homography'))
        if 'calibration_points' in member_cols:
            stmts.append(text('ALTER TABLE camera_group_members DROP COLUMN IF EXISTS calibration_points'))
        for column_name in ('crop_top', 'crop_bottom', 'crop_left', 'crop_right'):
            if column_name not in member_cols:
                stmts.append(
                    text(
                        f'ALTER TABLE camera_group_members '
                        f'ADD COLUMN IF NOT EXISTS {column_name} INTEGER NOT NULL DEFAULT 0'
                    )
                )
    elif dialect == 'sqlite':
        stmts = []
        if 'pipeline_mode' not in group_cols:
            stmts.append(text("ALTER TABLE camera_groups ADD COLUMN pipeline_mode VARCHAR(20) NOT NULL DEFAULT 'hybrid'"))
        for column_name in ('crop_top', 'crop_bottom', 'crop_left', 'crop_right'):
            if column_name not in member_cols:
                stmts.append(
                    text(f'ALTER TABLE camera_group_members ADD COLUMN {column_name} INTEGER NOT NULL DEFAULT 0')
                )
        if not stmts:
            return
    else:
        logger.warning(
            'schema_patches: unknown dialect %s — update camera_groups layout pipeline columns manually',
            dialect,
        )
        return

    try:
        with engine.begin() as conn:
            for stmt in stmts:
                conn.execute(stmt)
        _patch_done('ensured camera_groups layout pipeline schema')
    except Exception as err:
        logger.error('schema_patches: failed to ensure camera_groups layout pipeline schema: %s', err)
        raise


def _ensure_anchored_identities() -> None:
    try:
        inspector = inspect(engine)
        if inspector.has_table('anchored_identities'):
            return
    except Exception as err:
        logger.warning('schema_patches: could not inspect anchored_identities table: %s', err)
        return

    dialect = engine.dialect.name
    if dialect == 'postgresql':
        stmt = text(
            """
            CREATE TABLE IF NOT EXISTS anchored_identities (
                id SERIAL PRIMARY KEY,
                group_id INTEGER REFERENCES camera_groups(id) ON DELETE CASCADE,
                global_id VARCHAR(80) UNIQUE NOT NULL,
                ship_id VARCHAR(80),
                track_id VARCHAR(100),
                cam_a_id INTEGER REFERENCES cameras(id) ON DELETE SET NULL,
                cam_b_id INTEGER REFERENCES cameras(id) ON DELETE SET NULL,
                bbox_a JSONB NOT NULL,
                bbox_b JSONB,
                embedding BYTEA,
                embedding_shape JSONB,
                ocr_history JSONB,
                first_seen_at TIMESTAMPTZ NOT NULL,
                last_seen_at TIMESTAMPTZ NOT NULL,
                anchored_at TIMESTAMPTZ NOT NULL,
                last_track JSONB,
                confidence DOUBLE PRECISION,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
            """
        )
        index_stmts = [
            text('CREATE INDEX IF NOT EXISTS ix_anchored_identities_global_id ON anchored_identities(global_id)'),
            text('CREATE INDEX IF NOT EXISTS ix_anchored_identities_group_id ON anchored_identities(group_id)'),
            text('CREATE INDEX IF NOT EXISTS ix_anchored_identities_ship_id ON anchored_identities(ship_id)'),
        ]
    elif dialect == 'sqlite':
        stmt = text(
            """
            CREATE TABLE IF NOT EXISTS anchored_identities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER,
                global_id VARCHAR(80) UNIQUE NOT NULL,
                ship_id VARCHAR(80),
                track_id VARCHAR(100),
                cam_a_id INTEGER,
                cam_b_id INTEGER,
                bbox_a TEXT NOT NULL,
                bbox_b TEXT,
                embedding BLOB,
                embedding_shape TEXT,
                ocr_history TEXT,
                first_seen_at TIMESTAMP NOT NULL,
                last_seen_at TIMESTAMP NOT NULL,
                anchored_at TIMESTAMP NOT NULL,
                last_track TEXT,
                confidence REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        index_stmts = []
    else:
        logger.warning(
            'schema_patches: unknown dialect %s — create anchored_identities manually',
            dialect,
        )
        return

    try:
        with engine.begin() as conn:
            conn.execute(stmt)
            for index_stmt in index_stmts:
                conn.execute(index_stmt)
        _patch_done('ensured anchored_identities table')
    except Exception as err:
        logger.error('schema_patches: failed to create anchored_identities: %s', err)
        raise


def _ensure_sepay_port_configs() -> None:
    try:
        inspector = inspect(engine)
        if not inspector.has_table('port_configs'):
            return
    except Exception as err:
        logger.warning('schema_patches: could not inspect port_configs: %s', err)
        return

    from app.services.sepay_config_service import SEPAY_CONFIG_DEFAULTS

    dialect = engine.dialect.name
    if dialect == 'postgresql':
        stmt = text(
            """
            INSERT INTO port_configs (key, value, description)
            VALUES (:key, :value, :description)
            ON CONFLICT (key) DO NOTHING
            """
        )
    elif dialect == 'sqlite':
        stmt = text(
            """
            INSERT OR IGNORE INTO port_configs (key, value, description)
            VALUES (:key, :value, :description)
            """
        )
    else:
        logger.warning(
            'schema_patches: unknown dialect %s — seed sepay port_configs manually',
            dialect,
        )
        return

    try:
        with engine.begin() as conn:
            for key, (default_value, description) in SEPAY_CONFIG_DEFAULTS.items():
                conn.execute(
                    stmt,
                    {'key': key, 'value': default_value, 'description': description},
                )
        _patch_done('ensured sepay port_configs keys')
    except Exception as err:
        logger.error('schema_patches: failed to seed sepay port_configs: %s', err)
        raise


def _ensure_visual_stack_port_configs() -> None:
    try:
        inspector = inspect(engine)
        if not inspector.has_table('port_configs'):
            return
    except Exception as err:
        logger.warning('schema_patches: could not inspect port_configs: %s', err)
        return

    defaults = {
        'enable_visual_id': (
            'true',
            'Enable visual vessel identification (manual enrollment + vector search).',
        ),
        'visual_id_interval_sec': (
            '1.0',
            'Seconds between visual-id attempts for confirmed tracks.',
        ),
        'visual_min_crop_area': (
            '4096',
            'Minimum crop area (pixels) to run visual embedding extraction.',
        ),
        'visual_match_threshold': (
            '0.72',
            'Minimum similarity score to accept visual-id match.',
        ),
        'visual_margin_threshold': (
            '0.04',
            'Minimum top1-top2 score margin to avoid ambiguous visual matches.',
        ),
        'visual_top_k': (
            '5',
            'Number of nearest visual candidates returned from vector search.',
        ),
        'visual_model_path': (
            '',
            'Path to ViT/TorchScript model for visual embedding extraction.',
        ),
        'visual_backbone': (
            'vit_base_patch16_224',
            'Backbone model name for visual embedding extractor.',
        ),
        'visual_embedding_dim': (
            '1024',
            'Embedding dimension expected by visual model output.',
        ),
        'visual_batch_size': (
            '8',
            'Batch size for visual embedding extraction worker.',
        ),
        'visual_device': (
            '0',
            'Device for visual embedding extraction (`0`, `cuda:0`, or `cpu`).',
        ),
        'redis_url': (
            'redis://127.0.0.1:6379/0',
            'Redis URL used for runtime visual-id cache.',
        ),
        'redis_key_prefix': (
            'dock_manager',
            'Redis key prefix for visual-id runtime cache.',
        ),
        'redis_visual_ttl_sec': (
            '300',
            'TTL (seconds) for visual-id runtime cache entries.',
        ),
        'qdrant_host': (
            '127.0.0.1',
            'Qdrant host for visual embedding vector search.',
        ),
        'qdrant_port': (
            '6333',
            'Qdrant HTTP API port.',
        ),
        'qdrant_api_key': (
            '',
            'Qdrant API key (optional for secured deployments).',
        ),
        'qdrant_collection': (
            'vessel_visual_embeddings',
            'Qdrant collection used to store vessel visual embeddings.',
        ),
        'qdrant_vector_size': (
            '1024',
            'Vector dimension used by Qdrant collection.',
        ),
        'qdrant_distance': (
            'COSINE',
            'Distance metric used by Qdrant collection (COSINE / DOT / EUCLID).',
        ),
    }

    dialect = engine.dialect.name
    if dialect == 'postgresql':
        stmt = text(
            """
            INSERT INTO port_configs (key, value, description)
            VALUES (:key, :value, :description)
            ON CONFLICT (key) DO NOTHING
            """
        )
    elif dialect == 'sqlite':
        stmt = text(
            """
            INSERT OR IGNORE INTO port_configs (key, value, description)
            VALUES (:key, :value, :description)
            """
        )
    else:
        logger.warning(
            'schema_patches: unknown dialect %s — seed visual stack port_configs manually',
            dialect,
        )
        return

    try:
        with engine.begin() as conn:
            for key, (default_value, description) in defaults.items():
                conn.execute(
                    stmt,
                    {'key': key, 'value': default_value, 'description': description},
                )
        _patch_done('ensured visual stack port_configs keys')
    except Exception as err:
        logger.error('schema_patches: failed to seed visual stack port_configs: %s', err)
        raise


def _ensure_training_snapshot_port_configs() -> None:
    try:
        inspector = inspect(engine)
        if not inspector.has_table('port_configs'):
            return
    except Exception as err:
        logger.warning('schema_patches: could not inspect port_configs: %s', err)
        return

    defaults = {
        'enable_training_snapshot': (
            'false',
            'Enable saving full-quality vessel crops for model training.',
        ),
        'training_snapshot_interval_sec': (
            '5.0',
            'Seconds between training snapshot saves per camera.',
        ),
        'training_snapshot_base_dir': (
            'snapshot',
            'Directory under server/ for training data: ship_id crops, others/, and yolo/images+labels.',
        ),
        'training_snapshot_jpeg_quality': (
            '95',
            'JPEG quality (50-100) for training crops and YOLO full frames.',
        ),
    }

    dialect = engine.dialect.name
    if dialect == 'postgresql':
        stmt = text(
            """
            INSERT INTO port_configs (key, value, description)
            VALUES (:key, :value, :description)
            ON CONFLICT (key) DO NOTHING
            """
        )
    elif dialect == 'sqlite':
        stmt = text(
            """
            INSERT OR IGNORE INTO port_configs (key, value, description)
            VALUES (:key, :value, :description)
            """
        )
    else:
        logger.warning(
            'schema_patches: unknown dialect %s — seed training snapshot port_configs manually',
            dialect,
        )
        return

    try:
        with engine.begin() as conn:
            for key, (default_value, description) in defaults.items():
                conn.execute(
                    stmt,
                    {'key': key, 'value': default_value, 'description': description},
                )
            # Remove legacy snapshot threshold knobs (kept historically but no longer used).
            delete_keys = [
                'training_snapshot_min_ocr_confidence',
                'training_snapshot_min_visual_confidence',
            ]
            for k in delete_keys:
                conn.execute(
                    text('DELETE FROM port_configs WHERE key = :key'),
                    {'key': k},
                )
        _patch_done('ensured training snapshot port_configs keys')
    except Exception as err:
        logger.error('schema_patches: failed to seed training snapshot port_configs: %s', err)
        raise


def _ensure_fee_configs_berth_limit() -> None:
    try:
        inspector = inspect(engine)
        if not inspector.has_table('fee_configs'):
            return
        cols = {c['name'] for c in inspector.get_columns('fee_configs')}
        if 'berth_limit_count' in cols and 'berth_limit_unit' in cols:
            return
    except Exception as err:
        logger.warning('schema_patches: could not inspect fee_configs table: %s', err)
        return

    dialect = engine.dialect.name
    stmts = []
    if dialect == 'postgresql':
        stmts = [
            text('ALTER TABLE fee_configs ADD COLUMN IF NOT EXISTS berth_limit_count INTEGER'),
            text('ALTER TABLE fee_configs ADD COLUMN IF NOT EXISTS berth_limit_unit VARCHAR(10)'),
        ]
    elif dialect == 'sqlite':
        if 'berth_limit_count' not in cols:
            stmts.append(text('ALTER TABLE fee_configs ADD COLUMN berth_limit_count INTEGER'))
        if 'berth_limit_unit' not in cols:
            stmts.append(text('ALTER TABLE fee_configs ADD COLUMN berth_limit_unit VARCHAR(10)'))
    else:
        logger.warning(
            'schema_patches: unknown dialect %s — add fee_configs berth limit columns manually',
            dialect,
        )
        return

    if not stmts:
        return

    try:
        with engine.begin() as conn:
            for stmt in stmts:
                conn.execute(stmt)
        _patch_done('ensured fee_configs berth limit columns')
    except Exception as err:
        logger.error('schema_patches: failed to add fee_configs berth limit columns: %s', err)
        raise


def _ensure_fee_configs_penalty_fields() -> None:
    try:
        inspector = inspect(engine)
        if not inspector.has_table('fee_configs'):
            return
        cols = {c['name'] for c in inspector.get_columns('fee_configs')}
        needed = {'over_limit_penalty_amount', 'outside_hours_penalty_amount', 'operating_hours'}
        if needed.issubset(cols):
            return
    except Exception as err:
        logger.warning('schema_patches: could not inspect fee_configs table: %s', err)
        return

    dialect = engine.dialect.name
    stmts = []
    if dialect == 'postgresql':
        stmts = [
            text(
                'ALTER TABLE fee_configs ADD COLUMN IF NOT EXISTS '
                'over_limit_penalty_amount NUMERIC(12,2)'
            ),
            text(
                'ALTER TABLE fee_configs ADD COLUMN IF NOT EXISTS '
                'outside_hours_penalty_amount NUMERIC(12,2)'
            ),
            text('ALTER TABLE fee_configs ADD COLUMN IF NOT EXISTS operating_hours JSONB'),
        ]
    elif dialect == 'sqlite':
        if 'over_limit_penalty_amount' not in cols:
            stmts.append(text('ALTER TABLE fee_configs ADD COLUMN over_limit_penalty_amount NUMERIC(12,2)'))
        if 'outside_hours_penalty_amount' not in cols:
            stmts.append(
                text('ALTER TABLE fee_configs ADD COLUMN outside_hours_penalty_amount NUMERIC(12,2)')
            )
        if 'operating_hours' not in cols:
            stmts.append(text('ALTER TABLE fee_configs ADD COLUMN operating_hours JSON'))
    else:
        logger.warning(
            'schema_patches: unknown dialect %s — add fee_configs penalty columns manually',
            dialect,
        )
        return

    if not stmts:
        return

    try:
        with engine.begin() as conn:
            for stmt in stmts:
                conn.execute(stmt)
        _patch_done('ensured fee_configs penalty and operating_hours columns')
    except Exception as err:
        logger.error('schema_patches: failed to add fee_configs penalty columns: %s', err)
        raise


def _ensure_invoices_is_outside_operating_hours() -> None:
    try:
        inspector = inspect(engine)
        if not inspector.has_table('invoices'):
            return
        cols = {c['name'] for c in inspector.get_columns('invoices')}
        if 'is_outside_operating_hours' in cols:
            return
    except Exception as err:
        logger.warning('schema_patches: could not inspect invoices table: %s', err)
        return

    dialect = engine.dialect.name
    stmt = None
    if dialect == 'postgresql':
        stmt = text(
            'ALTER TABLE invoices ADD COLUMN IF NOT EXISTS '
            'is_outside_operating_hours BOOLEAN NOT NULL DEFAULT FALSE'
        )
    elif dialect == 'sqlite':
        stmt = text(
            'ALTER TABLE invoices ADD COLUMN is_outside_operating_hours BOOLEAN NOT NULL DEFAULT 0'
        )
    else:
        logger.warning(
            'schema_patches: unknown dialect %s — add invoices.is_outside_operating_hours manually',
            dialect,
        )
        return

    try:
        with engine.begin() as conn:
            conn.execute(stmt)
        _patch_done('added invoices.is_outside_operating_hours')
    except Exception as err:
        logger.error('schema_patches: failed to add invoices.is_outside_operating_hours: %s', err)
        raise


def _ensure_invoices_is_over_berth_limit() -> None:
    try:
        inspector = inspect(engine)
        if not inspector.has_table('invoices'):
            return
        cols = {c['name'] for c in inspector.get_columns('invoices')}
        if 'is_over_berth_limit' in cols:
            return
    except Exception as err:
        logger.warning('schema_patches: could not inspect invoices table: %s', err)
        return

    dialect = engine.dialect.name
    stmt = None
    if dialect == 'postgresql':
        stmt = text(
            'ALTER TABLE invoices ADD COLUMN IF NOT EXISTS is_over_berth_limit BOOLEAN NOT NULL DEFAULT FALSE'
        )
    elif dialect == 'sqlite':
        stmt = text(
            'ALTER TABLE invoices ADD COLUMN is_over_berth_limit BOOLEAN NOT NULL DEFAULT 0'
        )
    else:
        logger.warning(
            'schema_patches: unknown dialect %s — add invoices.is_over_berth_limit manually',
            dialect,
        )
        return

    try:
        with engine.begin() as conn:
            conn.execute(stmt)
        _patch_done('added invoices.is_over_berth_limit')
    except Exception as err:
        logger.error('schema_patches: failed to add invoices.is_over_berth_limit: %s', err)
        raise


def _ensure_invoices_discount_amount() -> None:
    try:
        inspector = inspect(engine)
        if not inspector.has_table('invoices'):
            return
        cols = {c['name'] for c in inspector.get_columns('invoices')}
    except Exception as err:
        logger.warning('schema_patches: could not inspect invoices table: %s', err)
        return

    if 'discount_amount' in cols:
        return

    dialect = engine.dialect.name
    if dialect == 'postgresql':
        stmt = text(
            'ALTER TABLE invoices ADD COLUMN IF NOT EXISTS discount_amount NUMERIC(12, 2) '
            "NOT NULL DEFAULT 0"
        )
    elif dialect == 'sqlite':
        stmt = text(
            'ALTER TABLE invoices ADD COLUMN discount_amount NUMERIC(12, 2) NOT NULL DEFAULT 0'
        )
    else:
        logger.warning(
            'schema_patches: unknown dialect %s — add invoices.discount_amount manually',
            dialect,
        )
        return

    try:
        with engine.begin() as conn:
            conn.execute(stmt)
        _patch_done('added invoices.discount_amount')
    except Exception as err:
        logger.error('schema_patches: failed to add invoices.discount_amount: %s', err)
        raise


def _ensure_invoices_discount_workflow() -> None:
    try:
        inspector = inspect(engine)
        if not inspector.has_table('invoices'):
            return
        cols = {c['name'] for c in inspector.get_columns('invoices')}
    except Exception as err:
        logger.warning('schema_patches: could not inspect invoices table: %s', err)
        return

    dialect = engine.dialect.name
    stmts = []
    if dialect == 'postgresql':
        if 'discount_requested_amount' not in cols:
            stmts.append(
                text(
                    'ALTER TABLE invoices ADD COLUMN IF NOT EXISTS discount_requested_amount '
                    'NUMERIC(12, 2) NOT NULL DEFAULT 0'
                )
            )
        if 'discount_status' not in cols:
            stmts.append(
                text(
                    "ALTER TABLE invoices ADD COLUMN IF NOT EXISTS discount_status "
                    "VARCHAR(20) NOT NULL DEFAULT 'none'"
                )
            )
        if 'discount_reviewed_at' not in cols:
            stmts.append(
                text(
                    'ALTER TABLE invoices ADD COLUMN IF NOT EXISTS discount_reviewed_at TIMESTAMPTZ'
                )
            )
        if 'discount_reviewed_by' not in cols:
            stmts.append(
                text(
                    'ALTER TABLE invoices ADD COLUMN IF NOT EXISTS discount_reviewed_by INTEGER '
                    'REFERENCES users(id) ON DELETE SET NULL'
                )
            )
        if 'discount_reject_reason' not in cols:
            stmts.append(
                text('ALTER TABLE invoices ADD COLUMN IF NOT EXISTS discount_reject_reason TEXT')
            )
    elif dialect == 'sqlite':
        if 'discount_requested_amount' not in cols:
            stmts.append(
                text(
                    'ALTER TABLE invoices ADD COLUMN discount_requested_amount '
                    'NUMERIC(12, 2) NOT NULL DEFAULT 0'
                )
            )
        if 'discount_status' not in cols:
            stmts.append(
                text(
                    "ALTER TABLE invoices ADD COLUMN discount_status VARCHAR(20) NOT NULL DEFAULT 'none'"
                )
            )
        if 'discount_reviewed_at' not in cols:
            stmts.append(text('ALTER TABLE invoices ADD COLUMN discount_reviewed_at DATETIME'))
        if 'discount_reviewed_by' not in cols:
            stmts.append(text('ALTER TABLE invoices ADD COLUMN discount_reviewed_by INTEGER'))
        if 'discount_reject_reason' not in cols:
            stmts.append(text('ALTER TABLE invoices ADD COLUMN discount_reject_reason TEXT'))
    else:
        logger.warning(
            'schema_patches: unknown dialect %s — add invoice discount workflow columns manually',
            dialect,
        )
        return

    if not stmts:
        return

    try:
        with engine.begin() as conn:
            for stmt in stmts:
                conn.execute(stmt)
            conn.execute(
                text(
                    """
                    UPDATE invoices
                    SET discount_status = 'approved',
                        discount_requested_amount = discount_amount
                    WHERE discount_amount > 0
                      AND (discount_status IS NULL OR discount_status = 'none')
                    """
                )
            )
        _patch_done('ensured invoice discount workflow columns')
    except Exception as err:
        logger.error('schema_patches: failed to add invoice discount workflow columns: %s', err)
        raise


def _ensure_invoices_financial_snapshots() -> None:
    try:
        inspector = inspect(engine)
        if not inspector.has_table('invoices'):
            return
        cols = {c['name'] for c in inspector.get_columns('invoices')}
    except Exception as err:
        logger.warning('schema_patches: could not inspect invoices table: %s', err)
        return

    dialect = engine.dialect.name
    stmts = []
    if dialect == 'postgresql':
        if 'vessel_ship_id_snapshot' not in cols:
            stmts.append(text('ALTER TABLE invoices ADD COLUMN IF NOT EXISTS vessel_ship_id_snapshot VARCHAR(50)'))
        if 'vessel_type_name_snapshot' not in cols:
            stmts.append(text('ALTER TABLE invoices ADD COLUMN IF NOT EXISTS vessel_type_name_snapshot VARCHAR(100)'))
        if 'financial_locked_at' not in cols:
            stmts.append(text('ALTER TABLE invoices ADD COLUMN IF NOT EXISTS financial_locked_at TIMESTAMPTZ'))
    elif dialect == 'sqlite':
        if 'vessel_ship_id_snapshot' not in cols:
            stmts.append(text('ALTER TABLE invoices ADD COLUMN vessel_ship_id_snapshot VARCHAR(50)'))
        if 'vessel_type_name_snapshot' not in cols:
            stmts.append(text('ALTER TABLE invoices ADD COLUMN vessel_type_name_snapshot VARCHAR(100)'))
        if 'financial_locked_at' not in cols:
            stmts.append(text('ALTER TABLE invoices ADD COLUMN financial_locked_at DATETIME'))
    else:
        logger.warning(
            'schema_patches: unknown dialect %s — add invoice snapshot columns manually',
            dialect,
        )
        return

    if not stmts:
        return

    try:
        with engine.begin() as conn:
            for stmt in stmts:
                conn.execute(stmt)
        _patch_done('ensured invoice financial snapshot columns')
    except Exception as err:
        logger.error('schema_patches: failed to add invoice snapshot columns: %s', err)
        raise


def _ensure_bulk_payment_sessions() -> None:
    try:
        inspector = inspect(engine)
        if inspector.has_table('bulk_payment_sessions'):
            return
    except Exception as err:
        logger.warning('schema_patches: could not inspect bulk_payment_sessions: %s', err)
        return

    dialect = engine.dialect.name
    if dialect == 'postgresql':
        stmt = text(
            """
            CREATE TABLE IF NOT EXISTS bulk_payment_sessions (
                id SERIAL PRIMARY KEY,
                reference_code VARCHAR(64) UNIQUE NOT NULL,
                invoice_ids JSONB NOT NULL,
                expected_total NUMERIC(12, 2) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                sepay_txn_id INTEGER,
                created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                completed_at TIMESTAMPTZ
            )
            """
        )
        index_stmt = text(
            'CREATE INDEX IF NOT EXISTS ix_bulk_payment_sessions_reference_code '
            'ON bulk_payment_sessions(reference_code)'
        )
    elif dialect == 'sqlite':
        stmt = text(
            """
            CREATE TABLE IF NOT EXISTS bulk_payment_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reference_code VARCHAR(64) UNIQUE NOT NULL,
                invoice_ids TEXT NOT NULL,
                expected_total NUMERIC(12, 2) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                sepay_txn_id INTEGER,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            )
            """
        )
        index_stmt = None
    else:
        logger.warning(
            'schema_patches: unknown dialect %s — create bulk_payment_sessions manually',
            dialect,
        )
        return

    try:
        with engine.begin() as conn:
            conn.execute(stmt)
            if index_stmt is not None:
                conn.execute(index_stmt)
        _patch_done('ensured bulk_payment_sessions table')
    except Exception as err:
        logger.error('schema_patches: failed to create bulk_payment_sessions: %s', err)
        raise


def _migrate_port_config_frames_to_seconds() -> None:
    """Convert legacy frame-based port_configs to second-based keys."""
    try:
        inspector = inspect(engine)
        if not inspector.has_table('port_configs'):
            return
    except Exception as err:
        logger.warning('schema_patches: could not inspect port_configs: %s', err)
        return

    from app.utils.port_timing_config import (
        DEFAULT_SEC_BY_KEY,
        FRAME_TO_SEC_KEY,
        LEGACY_FRAME_CONFIG_KEYS,
        frames_to_seconds,
    )

    dialect = engine.dialect.name
    if dialect == 'postgresql':
        upsert = text(
            """
            INSERT INTO port_configs (key, value, description)
            VALUES (:key, :value, :description)
            ON CONFLICT (key) DO UPDATE SET
                value = EXCLUDED.value,
                description = EXCLUDED.description
            """
        )
        delete_legacy = text('DELETE FROM port_configs WHERE key = :key')
    elif dialect == 'sqlite':
        upsert = text(
            """
            INSERT INTO port_configs (key, value, description)
            VALUES (:key, :value, :description)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                description = excluded.description
            """
        )
        delete_legacy = text('DELETE FROM port_configs WHERE key = :key')
    else:
        logger.warning(
            'schema_patches: unknown dialect %s — migrate frame port_configs manually',
            dialect,
        )
        return

    descriptions = {
        'ocr_interval_sec': 'Seconds between OCR attempts',
        'track_min_confirm_sec': 'Seconds before TENTATIVE becomes CONFIRMED',
        'track_max_tentative_sec': 'Seconds without match before tentative track is removed',
        'track_max_lost_sec': 'Seconds in LOST before track is removed',
    }

    try:
        with engine.begin() as conn:
            fps_row = conn.execute(
                text("SELECT value FROM port_configs WHERE key = 'record_fps' LIMIT 1")
            ).fetchone()
            try:
                fps = float(fps_row[0]) if fps_row and str(fps_row[0]).strip() else 20.0
            except (TypeError, ValueError):
                fps = 20.0
            fps = max(1.0, fps)

            for frame_key, sec_key in FRAME_TO_SEC_KEY.items():
                sec_row = conn.execute(
                    text('SELECT value FROM port_configs WHERE key = :key LIMIT 1'),
                    {'key': sec_key},
                ).fetchone()
                sec_value: str | None = None
                if sec_row and str(sec_row[0]).strip():
                    sec_value = str(sec_row[0]).strip()
                else:
                    frame_row = conn.execute(
                        text('SELECT value FROM port_configs WHERE key = :key LIMIT 1'),
                        {'key': frame_key},
                    ).fetchone()
                    if frame_row and str(frame_row[0]).strip():
                        try:
                            frames = float(str(frame_row[0]).strip())
                            sec_value = f'{frames_to_seconds(frames, fps):.4g}'
                        except ValueError:
                            sec_value = None
                    if sec_value is None:
                        sec_value = str(DEFAULT_SEC_BY_KEY[sec_key])

                conn.execute(
                    upsert,
                    {
                        'key': sec_key,
                        'value': sec_value,
                        'description': descriptions[sec_key],
                    },
                )

            for legacy_key in LEGACY_FRAME_CONFIG_KEYS:
                conn.execute(delete_legacy, {'key': legacy_key})

        _patch_done('migrated frame port_configs to seconds')
    except Exception as err:
        logger.error('schema_patches: failed to migrate frame port_configs: %s', err)
        raise


def apply_schema_patches(*, quiet: bool = False) -> list[str]:
    global _patch_quiet, _patch_applied
    _patch_quiet = quiet
    _patch_applied = []
    _ensure_invoices_deleted_at()
    _ensure_port_logs_ships_completed_today()
    _ensure_orders_total_amount()
    _ensure_invoices_creation_source()
    _ensure_detections_audit_image_path()
    _ensure_fee_configs_berth_limit()
    _ensure_fee_configs_penalty_fields()
    _ensure_invoices_is_over_berth_limit()
    _ensure_invoices_is_outside_operating_hours()
    _ensure_invoices_discount_amount()
    _ensure_invoices_discount_workflow()
    _ensure_invoices_financial_snapshots()
    _ensure_camera_groups()
    _ensure_camera_groups_layout_pipeline()
    _ensure_anchored_identities()
    _ensure_sepay_port_configs()
    _ensure_visual_stack_port_configs()
    _ensure_training_snapshot_port_configs()
    _migrate_port_config_frames_to_seconds()
    _ensure_bulk_payment_sessions()
    return list(_patch_applied)
