CREATE TABLE IF NOT EXISTS anchored_identities (
    id              SERIAL PRIMARY KEY,
    group_id        INTEGER REFERENCES camera_groups(id) ON DELETE CASCADE,
    global_id       VARCHAR(80) UNIQUE NOT NULL,
    ship_id         VARCHAR(80),
    track_id        VARCHAR(100),
    cam_a_id        INTEGER REFERENCES cameras(id) ON DELETE SET NULL,
    cam_b_id        INTEGER REFERENCES cameras(id) ON DELETE SET NULL,
    bbox_a          JSONB NOT NULL,
    bbox_b          JSONB,
    embedding       BYTEA,
    embedding_shape JSONB,
    ocr_history     JSONB,
    first_seen_at   TIMESTAMPTZ NOT NULL,
    last_seen_at    TIMESTAMPTZ NOT NULL,
    anchored_at     TIMESTAMPTZ NOT NULL,
    last_track      JSONB,
    confidence      DOUBLE PRECISION,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_anchored_identities_global_id ON anchored_identities(global_id);
CREATE INDEX IF NOT EXISTS ix_anchored_identities_group_id ON anchored_identities(group_id);
CREATE INDEX IF NOT EXISTS ix_anchored_identities_ship_id ON anchored_identities(ship_id);
