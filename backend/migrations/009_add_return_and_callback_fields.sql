-- ============================================================-- P1 核心流转修正迁移
-- 1. tickets 加 returned_to_user_id（退回目标人）
-- 2. tickets 加 callback_required / callback_details（回访相关）
-- ============================================================

ALTER TABLE tickets ADD COLUMN IF NOT EXISTS returned_to_user_id BIGINT REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS callback_required BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS callback_details TEXT;

CREATE INDEX IF NOT EXISTS idx_tickets_returned_to_user ON tickets(returned_to_user_id) WHERE returned_to_user_id IS NOT NULL;
