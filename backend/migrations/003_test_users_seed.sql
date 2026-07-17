-- ============================================================
-- 测试账号种子数据
-- 密码统一为 123456（bcrypt hash）
-- ============================================================

INSERT INTO users (id, username, name, role, group_id, is_group_leader, password_hash) VALUES
  (2, 'agent01',    '张技术',   'agent',    1, TRUE,  '$2b$12$F6GPMlPCu9NyJ0hFSC2zieMyclKwX4GiTqjFpxgaKS4QK.7iWwoF2'),
  (3, 'agent02',    '李客服',   'agent',    1, FALSE, '$2b$12$pI9PaBEJtEXorXjxo0/H8OrSWLpIRfGJb1QjZUoTtNGdcrOhZzvq.'),
  (4, 'agent03',    '王售后',   'agent',    1, FALSE, '$2b$12$w3B3fQ8VBclfoDEFVaHu3.2m1EKe6Z9mR3wgH3DD48NAER/Cj5Mke'),
  (5, 'handler01',  '赵工程师', 'handler',  1, FALSE, '$2b$12$gYUdKCLmrpIOXAKG1HQEQefC.R8SEVkcKF8N3hMRDQa/I0e3yJZ0S'),
  (6, 'handler02',  '钱工程师', 'handler',  1, FALSE, '$2b$12$3lwGuhCmgvc2WbseutQ1F.t0d1bX7zhLY5UCWEzGs.PQAGABFr3iO');

-- 用户-技能组关联
INSERT INTO user_skill_groups (user_id, skill_group_id) VALUES
  (2, 1),   -- 张技术 → 技术组
  (3, 2),   -- 李客服 → 市场组
  (4, 3),   -- 王售后 → 售后组
  (5, 1),   -- 赵工程师 → 技术组
  (6, 3);   -- 钱工程师 → 售后组

-- 重置序列
SELECT setval('users_id_seq', (SELECT MAX(id) FROM users));
