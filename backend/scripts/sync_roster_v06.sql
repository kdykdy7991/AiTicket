-- 客服工单系统用户表 V0.6 (20261103) 名册对齐
--
-- 目标：
--   1) 用户集合与 V0.6 名册一致（31 人）；名单外账号删除，例外保留
--      系统管理员 / 王耀宗 / 谢文倩 三人（用户确认保留）。
--   2) 按名册补齐投诉责任标记：部门负责人 complaint_leader、
--      分管领导 complaint_division_leader、负责的投诉类别 complaint_responsibilities。
--   3) 旧的「服务投诉协调人」占位账号与协调组随流程改造下线。
--
-- 前置：已在 /tmp/skdy_backup/ 做过 pg_dump 备份。
-- 执行：psql -v ON_ERROR_STOP=1 -f sync_roster_v06.sql
--
-- 部门名与库内既有对接部门不一致的（产品中心 vs 产品）本次不建人，
-- 见文件末尾「暂缓项」注释。

BEGIN;

-- ── 1. 待删除账号（V0.6 名册之外）────────────────────────────
CREATE TEMP TABLE del_users ON COMMIT DROP AS
SELECT id FROM users WHERE id IN (
    17,  20,  21,  22,  23,  28,  29,  30,  31,  32,  33,  34,
    36,  37, 200, 221, 228, 230, 231, 232, 234, 235, 236, 237,
    239, 240, 241, 243
);
-- 金鑫 / 徐挺 / 王颜 / 蒋超毅 / 金军 / 程伟 / 董明 / 乔永亮 / 汪军华 /
-- 张广瀚 / 吴小涵 / 乔兴达 / 楼豪丽 / 曹欣 / 服务投诉协调人 / 李晨阳 /
-- 销售处理人（占位） / 陈可意 / 姜敏 / 朱景升 / 丁伯华 / 于然 / 吴晨曦 /
-- 景亚楠 / 狄训飞 / 谢环环 / 赵文 / 高佳璐

-- ── 2. 引用这些账号的分类路由规则（2101 → 服务投诉协调人 200）──
DELETE FROM category_routing_rules
WHERE dispatcher_id IN (SELECT id FROM del_users)
   OR owner_id      IN (SELECT id FROM del_users);

-- ── 3. 与被删账号绑定的工单（级联文章 / 流转日志 / 节点提交 / SLA 轮次 / 钉钉通知）
DELETE FROM tickets
WHERE creator_id     IN (SELECT id FROM del_users)
   OR owner_id       IN (SELECT id FROM del_users)
   OR first_owner_id IN (SELECT id FROM del_users)
   OR dispatcher_id  IN (SELECT id FROM del_users);

-- ── 4. 留存工单上由被删账号产生的文章 / 流转 / 节点提交
-- 顺序要紧：ticket_node_submissions.article_id 外键指向 articles，
-- 所以先删节点提交，再删文章，最后删流转日志。
DELETE FROM ticket_node_submissions
 WHERE operator_id IN (SELECT id FROM del_users)
    OR article_id  IN (SELECT id FROM articles WHERE sender_id IN (SELECT id FROM del_users));
DELETE FROM articles              WHERE sender_id   IN (SELECT id FROM del_users);
DELETE FROM ticket_state_logs     WHERE operator_id IN (SELECT id FROM del_users);

-- ── 5. 删除账号本身（user_skill_groups 级联）
DELETE FROM users WHERE id IN (SELECT id FROM del_users);

-- ── 6. 下线旧「投诉协调」相关对接部门 ──────────────────────────
-- 100 服务投诉协调组：随「投诉协调人」流程改造下线，成员仅张华（其售后身份保留）。
-- 121 其他组：成员已全部移除，无分派链引用。
DELETE FROM skill_groups WHERE id IN (100, 121);

-- ── 7. 新建对接部门 ───────────────────────────────────────────
-- 时空道宇：CTO 丁晟（分管领导）+ 副总经理 陈国昌（部门负责人）
INSERT INTO skill_groups (id, name, created_at, updated_at) VALUES (122, '时空道宇', now(), now());
-- 售前与解决方案部：邱庆举（部门负责人）
INSERT INTO skill_groups (id, name, created_at, updated_at) VALUES (123, '售前与解决方案部', now(), now());

-- ── 8. 补建 V0.6 名册中缺失的账号 ─────────────────────────────
-- 密码沿用名册默认 skdy123（_SKDY_HASH）；local_login_enabled = true。
-- 贺巨方（产品中心）与库内「产品」部门名冲突，本轮不建，见末尾暂缓项。
INSERT INTO users (id, username, name, phone, password_hash, role, group_id,
                   is_group_leader, is_active, local_login_enabled, created_at, updated_at)
VALUES
 (245, 'dingsheng',   '丁晟',   NULL, '$2b$12$PlEUsC1JRHiZVoUdSUj4y.H/kzyqXWQ4jwfOkMMM3o2sb8.Bcnl/O', 'handler', 1, false, true, true, now(), now()),
 (246, 'chenguochao', '陈国昌', NULL, '$2b$12$PlEUsC1JRHiZVoUdSUj4y.H/kzyqXWQ4jwfOkMMM3o2sb8.Bcnl/O', 'handler', 1, false, true, true, now(), now()),
 (247, 'chennningning','陈宁宁',NULL, '$2b$12$PlEUsC1JRHiZVoUdSUj4y.H/kzyqXWQ4jwfOkMMM3o2sb8.Bcnl/O', 'handler', 1, false, true, true, now(), now()),
 (248, 'qiuqingju',   '邱庆举', NULL, '$2b$12$PlEUsC1JRHiZVoUdSUj4y.H/kzyqXWQ4jwfOkMMM3o2sb8.Bcnl/O', 'handler', 1, false, true, true, now(), now()),
 (249, 'jinguoyong',  '金国雍', NULL, '$2b$12$PlEUsC1JRHiZVoUdSUj4y.H/kzyqXWQ4jwfOkMMM3o2sb8.Bcnl/O', 'handler', 1, false, true, true, now(), now()),
 (250, 'fuchanghai',  '傅常海', NULL, '$2b$12$PlEUsC1JRHiZVoUdSUj4y.H/kzyqXWQ4jwfOkMMM3o2sb8.Bcnl/O', 'handler', 1, false, true, true, now(), now()),
 (251, 'qiusuchao',   '曲苏超', NULL, '$2b$12$PlEUsC1JRHiZVoUdSUj4y.H/kzyqXWQ4jwfOkMMM3o2sb8.Bcnl/O', 'handler', 1, false, true, true, now(), now()),
 (252, 'lihui',       '李慧',   NULL, '$2b$12$PlEUsC1JRHiZVoUdSUj4y.H/kzyqXWQ4jwfOkMMM3o2sb8.Bcnl/O', 'handler', 1, false, true, true, now(), now()),
 (253, 'liqingxin',   '李庆新', NULL, '$2b$12$PlEUsC1JRHiZVoUdSUj4y.H/kzyqXWQ4jwfOkMMM3o2sb8.Bcnl/O', 'handler', 1, false, true, true, now(), now());

-- ── 9. 补建成员标记 ───────────────────────────────────────────
-- complaint_leader            部门负责人
-- complaint_division_leader   分管领导
-- complaint_responsibilities  该负责人负责的投诉类别（2103 用）
INSERT INTO user_skill_groups
 (user_id, skill_group_id, is_dispatcher, complaint_leader, complaint_division_leader,
  complaint_responsibilities, effective_from, effective_to)
VALUES
 -- 丁晟：时空道宇 CTO，分管领导（2104 重大投诉）
 (245, 122, false, false, true, '[]'::json, NULL, NULL),
 -- 陈国昌：时空道宇 副总经理，渠道相关的重要投诉
 (246, 122, false, true,  false, '["渠道相关的重要投诉"]'::json, NULL, NULL),
 -- 陈宁宁：品牌传播与大客户，媒体相关的重要投诉
 (247,   1, false, true,  false, '["媒体相关的重要投诉"]'::json, NULL, NULL),
 -- 邱庆举：售前与解决方案部，售前与解决方案业务投诉
 (248, 123, false, true,  false, '["售前与解决方案业务投诉"]'::json, NULL, NULL),
 -- 金国雍：星座营销中心，海洋应用业务投诉
 (249,   7, false, true,  false, '["海洋应用业务投诉"]'::json, NULL, NULL),
 -- 傅常海：星座营销中心，产品线投诉（名册部门列留空，按投诉归属归入星座营销中心）
 (250,   7, false, true,  false, '["产品线投诉"]'::json, NULL, NULL),
 -- 曲苏超：星座营销中心，高精定位应用投诉（名册部门列留空，按投诉归属归入星座营销中心）
 (251,   7, false, true,  false, '["高精定位应用投诉"]'::json, NULL, NULL);

-- 李慧 / 李庆新：名册未给部门，暂不挂对接部门（无组则不可被分派）

-- ── 10. 补齐既有账号的标记 ────────────────────────────────────
-- 杨冰：客户服务组负责人（2102 一般投诉），此前责任类别为空
UPDATE user_skill_groups
   SET complaint_responsibilities = '["客户服务组负责人"]'::json
 WHERE user_id = 35 AND skill_group_id = 119;

-- 谢志鹏：名册指定为市场生态部部门对接人，账号此前被停用，恢复启用
UPDATE users SET is_active = true WHERE id = 11;

-- ── 11. 序列校准 ──────────────────────────────────────────────
SELECT setval('users_id_seq', (SELECT MAX(id) FROM users));
SELECT setval('skill_groups_id_seq', (SELECT MAX(id) FROM skill_groups));

COMMIT;

-- ── 暂缓项（部门名冲突，本轮未处理）────────────────────────────
-- 贺巨方 / 产品中心重要投诉：名册部门「产品中心」，库内对接部门为「产品」（v2 改名）。
--   需业务确认最终名后二选一：
--     a) 库内 skill_groups(3) 由「产品」改回「产品中心」，贺巨方入组；
--     b) 保留「产品」，贺巨方入组，投诉项名「产品中心重要投诉」维持不变。
-- 其余名册部门名与库内不一致（仅影响下拉显示，不影响功能）：
--   交付&售后 vs 售后 / 系统与网络运维 vs 客户服务组 /
--   经营管理 vs 经营管理部 / 研发中心 vs 终端研发 / 整星产品（星空智联）vs 整星产品
-- 名册未给部门的处理人：李慧、李庆新（已建账号，未挂对接部门）。
-- 名册未覆盖、删除后为空或缺人的部门：
--   星空智联行销部（8，成员全删）/ 销售（120，商机流程用，成员全删）/
--   产品（3，仅剩张朝娟）/ 财务（113，仅剩练露）/ 时空道宇（122）/ 售前与解决方案部（123）
