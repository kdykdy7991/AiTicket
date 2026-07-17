-- ============================================================
-- 归档改造迁移
-- 1. tickets 加 archive_notes（归档备注）
-- 2. tickets 加 is_callbacked（是否已回访，用于归档后筛选）
-- ============================================================

ALTER TABLE tickets ADD COLUMN IF NOT EXISTS archive_notes TEXT;
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS is_callbacked BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_tickets_is_callbacked ON tickets(is_callbacked) WHERE is_callbacked = TRUE;
