ALTER TABLE camera_groups
    ADD COLUMN IF NOT EXISTS pipeline_mode VARCHAR(20) NOT NULL DEFAULT 'hybrid';

UPDATE camera_groups
SET fusion_mode = 'layout'
WHERE fusion_mode <> 'layout';

ALTER TABLE camera_groups
    DROP CONSTRAINT IF EXISTS chk_camera_groups_fusion_mode;

ALTER TABLE camera_groups
    ADD CONSTRAINT chk_camera_groups_fusion_mode CHECK (fusion_mode IN ('layout'));

ALTER TABLE camera_groups
    DROP CONSTRAINT IF EXISTS chk_camera_groups_pipeline_mode;

ALTER TABLE camera_groups
    ADD CONSTRAINT chk_camera_groups_pipeline_mode CHECK (pipeline_mode IN ('hybrid', 'fused'));

ALTER TABLE camera_groups
    DROP COLUMN IF EXISTS stitch_metadata;

ALTER TABLE camera_group_members
    DROP COLUMN IF EXISTS homography,
    DROP COLUMN IF EXISTS calibration_points;
