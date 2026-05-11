CREATE TABLE IF NOT EXISTS camera_groups (
    id            SERIAL PRIMARY KEY,
    name          VARCHAR(120) UNIQUE NOT NULL,
    description   TEXT,
    fusion_mode   VARCHAR(20) NOT NULL DEFAULT 'layout',
    pipeline_mode VARCHAR(20) NOT NULL DEFAULT 'hybrid',
    canvas_width  INTEGER NOT NULL DEFAULT 1920,
    canvas_height INTEGER NOT NULL DEFAULT 1080,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_by    INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT chk_camera_groups_fusion_mode CHECK (fusion_mode IN ('layout')),
    CONSTRAINT chk_camera_groups_pipeline_mode CHECK (pipeline_mode IN ('hybrid', 'fused'))
);

CREATE TABLE IF NOT EXISTS camera_group_members (
    id                 SERIAL PRIMARY KEY,
    group_id           INTEGER NOT NULL REFERENCES camera_groups(id) ON DELETE CASCADE,
    camera_id          INTEGER NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    role               VARCHAR(20) NOT NULL DEFAULT 'tile',
    priority           INTEGER NOT NULL DEFAULT 0,
    layout_x           INTEGER NOT NULL DEFAULT 0,
    layout_y           INTEGER NOT NULL DEFAULT 0,
    layout_w           INTEGER,
    layout_h           INTEGER,
    layout_rotation    REAL NOT NULL DEFAULT 0,
    crop_top           INTEGER NOT NULL DEFAULT 0,
    crop_bottom        INTEGER NOT NULL DEFAULT 0,
    crop_left          INTEGER NOT NULL DEFAULT 0,
    crop_right         INTEGER NOT NULL DEFAULT 0,
    enabled            BOOLEAN NOT NULL DEFAULT TRUE,
    created_at         TIMESTAMPTZ DEFAULT NOW(),
    updated_at         TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(group_id, camera_id),
    CONSTRAINT chk_camera_group_members_role CHECK (role IN ('base', 'overlay', 'tile'))
);

CREATE INDEX IF NOT EXISTS ix_camera_group_members_group ON camera_group_members(group_id);
CREATE INDEX IF NOT EXISTS ix_camera_group_members_camera ON camera_group_members(camera_id);
