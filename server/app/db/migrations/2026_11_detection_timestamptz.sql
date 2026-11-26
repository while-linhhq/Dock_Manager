-- Chỉ chạy sau khi xác minh dữ liệu cũ là UTC, backup và restore thử thành công.
-- Thử trên DB bản sao trước; không chạy tự động trên DB hệ thống.
BEGIN;

SET LOCAL TIME ZONE 'UTC';

ALTER TABLE detections
    ALTER COLUMN start_time TYPE TIMESTAMPTZ
        USING start_time AT TIME ZONE 'UTC',
    ALTER COLUMN end_time TYPE TIMESTAMPTZ
        USING end_time AT TIME ZONE 'UTC';

COMMIT;
