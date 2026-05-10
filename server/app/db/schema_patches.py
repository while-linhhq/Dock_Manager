"""
Idempotent schema adjustments for existing databases (ORM create_all does not ALTER).

Keeps dev/prod DBs aligned when new columns are added to models before formal migrations.
"""

import logging

from sqlalchemy import inspect, text

from app.db.session import engine

logger = logging.getLogger(__name__)


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
        logger.info('schema_patches: added invoices.deleted_at')
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
        logger.info('schema_patches: added port_logs.ships_completed_today')
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
        logger.info('schema_patches: added orders.total_amount')
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
        logger.info('schema_patches: added invoices.creation_source')
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
        logger.info('schema_patches: added detections.audit_image_path')
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
                canvas_width INTEGER NOT NULL DEFAULT 1920,
                canvas_height INTEGER NOT NULL DEFAULT 1080,
                stitch_metadata JSONB,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                CONSTRAINT chk_camera_groups_fusion_mode
                    CHECK (fusion_mode IN ('layout', 'homography', 'panorama'))
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
                homography JSONB,
                calibration_points JSONB,
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
        logger.info('schema_patches: ensured camera_groups tables')
    except Exception as err:
        logger.error('schema_patches: failed to ensure camera_groups tables: %s', err)
        raise


def _ensure_camera_groups_stitch_metadata() -> None:
    try:
        inspector = inspect(engine)
        if not inspector.has_table('camera_groups'):
            return
        cols = {c['name'] for c in inspector.get_columns('camera_groups')}
        if 'stitch_metadata' in cols:
            return
    except Exception as err:
        logger.warning('schema_patches: could not inspect camera_groups table: %s', err)
        return

    dialect = engine.dialect.name
    if dialect == 'postgresql':
        stmt = text('ALTER TABLE camera_groups ADD COLUMN IF NOT EXISTS stitch_metadata JSONB')
    elif dialect == 'sqlite':
        stmt = text('ALTER TABLE camera_groups ADD COLUMN stitch_metadata JSON')
    else:
        logger.warning(
            'schema_patches: unknown dialect %s — add camera_groups.stitch_metadata manually',
            dialect,
        )
        return

    try:
        with engine.begin() as conn:
            conn.execute(stmt)
        logger.info('schema_patches: added camera_groups.stitch_metadata')
    except Exception as err:
        logger.error('schema_patches: failed to add camera_groups.stitch_metadata: %s', err)
        raise


def _ensure_camera_groups_panorama_mode() -> None:
    try:
        inspector = inspect(engine)
        if not inspector.has_table('camera_groups'):
            return
    except Exception as err:
        logger.warning('schema_patches: could not inspect camera_groups table: %s', err)
        return

    if engine.dialect.name != 'postgresql':
        return

    try:
        with engine.begin() as conn:
            conn.execute(text('ALTER TABLE camera_groups DROP CONSTRAINT IF EXISTS chk_camera_groups_fusion_mode'))
            conn.execute(
                text(
                    """
                    ALTER TABLE camera_groups
                    ADD CONSTRAINT chk_camera_groups_fusion_mode
                    CHECK (fusion_mode IN ('layout', 'homography', 'panorama'))
                    """
                )
            )
        logger.info('schema_patches: ensured camera_groups panorama fusion_mode')
    except Exception as err:
        logger.error('schema_patches: failed to update camera_groups fusion_mode constraint: %s', err)
        raise


def apply_schema_patches() -> None:
    _ensure_invoices_deleted_at()
    _ensure_port_logs_ships_completed_today()
    _ensure_orders_total_amount()
    _ensure_invoices_creation_source()
    _ensure_detections_audit_image_path()
    _ensure_camera_groups()
    _ensure_camera_groups_stitch_metadata()
    _ensure_camera_groups_panorama_mode()
