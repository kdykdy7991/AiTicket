-- 理清测试账号：客服只在客服组，部门人员只在技能组，互斥
-- 客服（agent）：清除技能组关联
DELETE FROM user_skill_groups WHERE user_id IN (2, 3, 4, 7, 8);  -- agent01/02/03/xwq/testrefresh

-- 部门人员（handler）：清除客服组归属
UPDATE users SET group_id = NULL WHERE role = 'handler' AND id IN (5, 6);

-- 重新配置部门人员技能组归属（确保每组有对接人和处理人）
-- 先清空 handler 的技能组关联，再重新插
DELETE FROM user_skill_groups WHERE user_id IN (5, 6);

-- handler01 赵工程师：技术组对接人
INSERT INTO user_skill_groups (user_id, skill_group_id, is_dispatcher) VALUES
  (5, 1, TRUE);   -- 技术组对接人

-- handler02 钱工程师：售后组处理人
INSERT INTO user_skill_groups (user_id, skill_group_id, is_dispatcher) VALUES
  (6, 3, FALSE);  -- 售后组处理人

-- 补一个市场组对接人（用 handler 角色，新建账号 market_dispatch）
-- 密码 123456
INSERT INTO users (id, username, name, role, group_id, is_group_leader, is_active, password_hash)
VALUES (9, 'market01', '周市场', 'handler', NULL, FALSE, TRUE,
        '$2b$12$ZzVrvzRrT0XE/8T79BEdb.teffcxsQL4qWxGbVacn3jiSMLiBQB8u')
ON CONFLICT (id) DO NOTHING;
INSERT INTO user_skill_groups (user_id, skill_group_id, is_dispatcher) VALUES
  (9, 2, TRUE)  -- 市场组对接人
ON CONFLICT DO NOTHING;

-- 补一个技术组处理人
INSERT INTO users (id, username, name, role, group_id, is_group_leader, is_active, password_hash)
VALUES (10, 'tech02', '吴技术', 'handler', NULL, FALSE, TRUE,
        '$2b$12$ZzVrvzRrT0XE/8T79BEdb.teffcxsQL4qWxGbVacn3jiSMLiBQB8u')
ON CONFLICT (id) DO NOTHING;
INSERT INTO user_skill_groups (user_id, skill_group_id, is_dispatcher) VALUES
  (10, 1, FALSE)  -- 技术组处理人
ON CONFLICT DO NOTHING;

-- 删除测试刷新账号（之前测试建的）
DELETE FROM user_skill_groups WHERE user_id = 8;
DELETE FROM users WHERE id = 8 AND username = 'testrefresh';

SELECT setval('users_id_seq', (SELECT MAX(id) FROM users));
