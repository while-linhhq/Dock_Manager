-- Run once on existing databases (PostgreSQL).
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
