-- ============================================================
-- 状态机重构迁移
-- 1. user_skill_groups 加 is_dispatcher（部门对接人标记）
-- 2. tickets 加 dispatcher_id（部门对接人）、hold_until（暂缓到时间）
-- 3. 状态枚举：去掉 awaiting_callback（待回访），新增 archived（已归档）
--    callbacked 从终态改为中间态
-- ============================================================

-- 1. user_skill_groups 加对接人标记
ALTER TABLE user_skill_groups ADD COLUMN IF NOT EXISTS is_dispatcher BOOLEAN NOT NULL DEFAULT FALSE;

-- 2. tickets 加字段
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS dispatcher_id BIGINT REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS hold_until TIMESTAMPTZ;

-- 3. 迁移已有数据：awaiting_callback → callbacked（待回访的当作已回访）
UPDATE tickets SET state = 'callbacked' WHERE state = 'awaiting_callback';

-- 4. 修改状态 CHECK 约束：去 awaiting_callback，加 archived
ALTER TABLE tickets DROP CONSTRAINT IF EXISTS chk_ticket_state;
ALTER TABLE tickets ADD CONSTRAINT chk_ticket_state CHECK (state IN (
    'pending', 'open', 'resolved', 'on_hold',
    'callbacked', 'archived', 'returned', 'cancelled'
));

-- 5. dispatcher_id 索引
CREATE INDEX IF NOT EXISTS idx_tickets_dispatcher ON tickets(dispatcher_id) WHERE dispatcher_id IS NOT NULL;

-- 6. 给现有技能组成员标记对接人（每个技能组第一个成员默认为对接人，便于测试）
-- 技术组：handler01(5) 标记为对接人；市场组：agent02(3)；售后组：agent03(4)
UPDATE user_skill_groups SET is_dispatcher = TRUE
WHERE (user_id, skill_group_id) IN
      ((SELECT id FROM users WHERE username='handler01'), (SELECT id FROM skill_groups WHERE name='技术组')),
      ((SELECT id FROM users WHERE username='agent02'), (SELECT id FROM skill_groups WHERE name='市场组')),
      ((SELECT id FROM users WHERE username='agent03'), (SELECT id FROM skill_groups WHERE name='售后组'));
