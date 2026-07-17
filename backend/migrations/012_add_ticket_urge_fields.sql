-- ============================================================-- 催办功能迁移
-- 1. tickets 加 urged_at（催办时间）
-- 2. tickets 加 urged_by_id（催办人）
-- ============================================================

ALTER TABLE tickets ADD COLUMN IF NOT EXISTS urged_at TIMESTAMPTZ;
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS urged_by_id BIGINT REFERENCES users(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_tickets_urged_at ON tickets(urged_at) WHERE urged_at IS NOT NULL;
