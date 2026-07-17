-- ============================================================
-- Skdy 工单系统一期 — 数据库建表脚本
-- Target: PostgreSQL 15
-- Date: 2026-06-16
-- Based on: PRD-工单系统一期.md v1.0
-- ============================================================

-- ============================================================
-- 1. 用户与组织
-- ============================================================

-- 客服组
CREATE TABLE groups (
    id          BIGSERIAL       PRIMARY KEY,
    name        VARCHAR(100)    NOT NULL UNIQUE,
    dingtalk_webhook_url VARCHAR(500),            -- 钉钉群机器人 Webhook
    created_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- 技能组
CREATE TABLE skill_groups (
    id          BIGSERIAL       PRIMARY KEY,
    name        VARCHAR(100)    NOT NULL UNIQUE,
    dingtalk_webhook_url VARCHAR(500),            -- 技能组钉钉群 Webhook
    created_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- 用户
CREATE TABLE users (
    id                  BIGSERIAL       PRIMARY KEY,
    username            VARCHAR(50)     NOT NULL UNIQUE,      -- 登录名
    name                VARCHAR(100)    NOT NULL,             -- 显示名
    phone               VARCHAR(20),                          -- 手机号（可选）
    password_hash       VARCHAR(255)    NOT NULL,             -- bcrypt hash
    role                VARCHAR(20)     NOT NULL DEFAULT 'agent',  -- admin / agent / handler
    group_id            BIGINT          REFERENCES groups(id) ON DELETE SET NULL,
    is_group_leader     BOOLEAN         NOT NULL DEFAULT FALSE,
    is_active           BOOLEAN         NOT NULL DEFAULT TRUE,
    dingtalk_id         VARCHAR(100),                         -- 钉钉用户 ID（用于工作通知）
    last_login_at       TIMESTAMPTZ,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_users_role CHECK (role IN ('admin', 'agent', 'handler'))
);

CREATE INDEX idx_users_group ON users(group_id);
CREATE INDEX idx_users_role ON users(role) WHERE is_active = TRUE;
CREATE INDEX idx_users_dingtalk ON users(dingtalk_id) WHERE dingtalk_id IS NOT NULL;

-- 用户-技能组 多对多
CREATE TABLE user_skill_groups (
    user_id         BIGINT      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    skill_group_id  BIGINT      NOT NULL REFERENCES skill_groups(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, skill_group_id)
);

-- ============================================================
-- 2. 工单分类与区域
-- ============================================================

-- 工单分类（树形结构：一级 → 二级）
CREATE TABLE ticket_categories (
    id          BIGSERIAL       PRIMARY KEY,
    parent_id   BIGINT          REFERENCES ticket_categories(id) ON DELETE CASCADE,
    name        VARCHAR(100)    NOT NULL,
    level       SMALLINT        NOT NULL DEFAULT 1,            -- 1=一级, 2=二级
    sort_order  INT             NOT NULL DEFAULT 0,
    is_active   BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_category_level CHECK (level IN (1, 2)),
    CONSTRAINT chk_category_parent CHECK (
        (level = 1 AND parent_id IS NULL) OR
        (level = 2 AND parent_id IS NOT NULL)
    )
);

CREATE INDEX idx_categories_parent ON ticket_categories(parent_id);
CREATE INDEX idx_categories_active ON ticket_categories(is_active) WHERE is_active = TRUE;

-- 区域（树形结构：省 → 市 → 区县 → 站点）
CREATE TABLE regions (
    id          BIGSERIAL       PRIMARY KEY,
    parent_id   BIGINT          REFERENCES regions(id) ON DELETE CASCADE,
    name        VARCHAR(100)    NOT NULL,
    level       SMALLINT        NOT NULL,                      -- 1=省, 2=市, 3=区县, 4=站点
    code        VARCHAR(20),                                    -- 行政区划代码
    sort_order  INT             NOT NULL DEFAULT 0,
    is_active   BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_region_level CHECK (level IN (1, 2, 3, 4))
);

CREATE INDEX idx_regions_parent ON regions(parent_id);
CREATE INDEX idx_regions_level  ON regions(level);
CREATE INDEX idx_regions_active ON regions(is_active) WHERE is_active = TRUE;

-- ============================================================
-- 3. 工单
-- ============================================================

-- 工单状态枚举说明：
--   pending            待受理
--   open               处理中
--   resolved           已处理
--   awaiting_callback  待回访
--   callbacked         已回访（终态）
--   returned           退回
--   on_hold            挂起
--   cancelled          已撤销（终态）

-- 工单优先级枚举说明：
--   p1_urgent          P1 特别重大事件
--   p2_high            P2 重大事件
--   p3_normal          P3 较大事件
--   p4_enterprise      P4 一般事件

-- 渠道来源枚举说明：
--   phone              电话
--   wechat             微信服务号
--   web                Web
--   app                App

CREATE TABLE tickets (
    id                          BIGSERIAL       PRIMARY KEY,
    number                      VARCHAR(20)     NOT NULL UNIQUE,     -- TKT-00001 格式
    title                       VARCHAR(500)    NOT NULL,
    description                 TEXT            NOT NULL DEFAULT '',

    -- 状态与优先级
    state                       VARCHAR(30)     NOT NULL DEFAULT 'pending',
    priority                    VARCHAR(20)     NOT NULL DEFAULT 'p4_enterprise',
    channel                     VARCHAR(20)     NOT NULL DEFAULT 'phone',

    -- 客户信息
    customer_type               VARCHAR(20)     NOT NULL DEFAULT 'personal', -- personal / enterprise
    customer_name               VARCHAR(100)    NOT NULL,
    customer_phone              VARCHAR(20)     NOT NULL,
    customer_company            VARCHAR(200),                        -- 所属公司
    customer_level              VARCHAR(20)     DEFAULT 'normal',    -- normal / vip / vvip
    device_sn                   VARCHAR(100),                        -- 设备编号/终端SN
    region_id                   BIGINT          REFERENCES regions(id) ON DELETE SET NULL,
    symptom                     TEXT,                                 -- 故障现象描述

    -- 分类与归属
    category_id                 BIGINT          REFERENCES ticket_categories(id) ON DELETE SET NULL,
    group_id                    BIGINT          REFERENCES groups(id) ON DELETE SET NULL,          -- 客服组
    skill_group_id              BIGINT          REFERENCES skill_groups(id) ON DELETE SET NULL,    -- 技能组
    owner_id                    BIGINT          REFERENCES users(id) ON DELETE SET NULL,           -- 当前负责人
    creator_id                  BIGINT          NOT NULL REFERENCES users(id) ON DELETE RESTRICT,  -- 创建人
    first_owner_id              BIGINT          REFERENCES users(id) ON DELETE SET NULL,           -- 首次受理坐席

    -- 重复/升级
    is_duplicate                BOOLEAN         NOT NULL DEFAULT FALSE,
    is_escalated                BOOLEAN         NOT NULL DEFAULT FALSE,
    duplicate_reason            TEXT,                                 -- 重投原因
    linked_ticket_id            BIGINT          REFERENCES tickets(id) ON DELETE SET NULL,         -- 关联的原始工单

    -- SLA
    first_response_deadline     TIMESTAMPTZ,                          -- 首次响应截止时间
    solution_deadline           TIMESTAMPTZ,                          -- 解决截止时间
    first_response_at           TIMESTAMPTZ,                          -- 首次响应实际时间
    solved_at                   TIMESTAMPTZ,                          -- 标记已处理的时间
    sla_first_response_breached BOOLEAN         NOT NULL DEFAULT FALSE,
    sla_solution_breached       BOOLEAN         NOT NULL DEFAULT FALSE,

    -- 结案
    closed_at                   TIMESTAMPTZ,                          -- 结案时间（已回访/已撤销）
    closed_duration_minutes     INT,                                   -- 结案耗时（分钟）

    -- 解决信息
    resolved                    BOOLEAN         NOT NULL DEFAULT FALSE,
    resolution                  TEXT,                                  -- 解决方案/处理备注

    -- 时间戳
    created_at                  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_ticket_state CHECK (state IN (
        'pending', 'open', 'resolved', 'awaiting_callback', 'callbacked',
        'returned', 'on_hold', 'cancelled'
    )),
    CONSTRAINT chk_ticket_priority CHECK (priority IN (
        'p1_urgent', 'p2_high', 'p3_normal', 'p4_enterprise'
    )),
    CONSTRAINT chk_ticket_channel CHECK (channel IN (
        'phone', 'wechat', 'web', 'app'
    )),
    CONSTRAINT chk_ticket_customer_type CHECK (customer_type IN (
        'personal', 'enterprise'
    )),
    CONSTRAINT chk_ticket_customer_level CHECK (customer_level IN (
        'normal', 'vip', 'vvip'
    )),
    CONSTRAINT chk_duplicate_reason CHECK (
        is_duplicate = FALSE OR duplicate_reason IS NOT NULL
    )
);

-- 工单编号序列（用于生成 TKT-00001 格式）
CREATE SEQUENCE ticket_number_seq START 1;

-- 核心查询索引
CREATE INDEX idx_tickets_state       ON tickets(state);
CREATE INDEX idx_tickets_priority    ON tickets(priority);
CREATE INDEX idx_tickets_owner       ON tickets(owner_id) WHERE state NOT IN ('callbacked', 'cancelled');
CREATE INDEX idx_tickets_creator     ON tickets(creator_id);
CREATE INDEX idx_tickets_group       ON tickets(group_id);
CREATE INDEX idx_tickets_skill_group ON tickets(skill_group_id);
CREATE INDEX idx_tickets_category    ON tickets(category_id);
CREATE INDEX idx_tickets_created     ON tickets(created_at DESC);
CREATE INDEX idx_tickets_customer_phone ON tickets(customer_phone);

-- SLA 超时检测索引：查找即将超时或已超时的工单
CREATE INDEX idx_tickets_sla_first_response ON tickets(first_response_deadline)
    WHERE state = 'pending' AND first_response_at IS NULL;
CREATE INDEX idx_tickets_sla_solution ON tickets(solution_deadline)
    WHERE state = 'open' AND solved_at IS NULL;

-- Dashboard 概览索引：待受理 + 未分配
CREATE INDEX idx_tickets_pending_unassigned ON tickets(created_at DESC)
    WHERE state = 'pending' AND owner_id IS NULL;
-- 挂起工单
CREATE INDEX idx_tickets_on_hold ON tickets(created_at DESC)
    WHERE state = 'on_hold';
-- 升级/重复工单
CREATE INDEX idx_tickets_escalated ON tickets(created_at DESC)
    WHERE is_duplicate = TRUE OR is_escalated = TRUE;

-- ============================================================
-- 4. 工单沟通记录（Article）
-- ============================================================

-- Article 类型说明：
--   reply           回复
--   internal_note   内 note（仅坐席和管理员可见）
--   addition        追加（需填写追加原因）
--   reminder        催办

CREATE TABLE articles (
    id              BIGSERIAL       PRIMARY KEY,
    ticket_id       BIGINT          NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    type            VARCHAR(20)     NOT NULL DEFAULT 'reply',
    sender_id       BIGINT          NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    subject         VARCHAR(500),                          -- 可选标题
    body            TEXT            NOT NULL DEFAULT '',
    internal        BOOLEAN         NOT NULL DEFAULT FALSE,        -- 是否内部可见（内 note 为 TRUE）
    append_reason   TEXT,                                          -- 追加原因（type=addition 时必填）
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_article_type CHECK (type IN (
        'reply', 'internal_note', 'addition', 'reminder'
    )),
    CONSTRAINT chk_addition_reason CHECK (
        type != 'addition' OR append_reason IS NOT NULL
    ),
    CONSTRAINT chk_internal_note CHECK (
        type != 'internal_note' OR internal = TRUE
    )
);

CREATE INDEX idx_articles_ticket   ON articles(ticket_id, created_at);
CREATE INDEX idx_articles_sender   ON articles(sender_id);
CREATE INDEX idx_articles_type     ON articles(ticket_id, type);

-- ============================================================
-- 5. 工单状态流转记录
-- ============================================================

CREATE TABLE ticket_state_logs (
    id                  BIGSERIAL       PRIMARY KEY,
    ticket_id           BIGINT          NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    from_state          VARCHAR(30),                                -- NULL 表示初始创建
    to_state            VARCHAR(30)     NOT NULL,
    operator_id         BIGINT          NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    reason              TEXT,                                       -- 退回原因 / 挂起原因等
    duration_minutes    INT,                                        -- 在 from_state 停留的分钟数
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_state_logs_ticket ON ticket_state_logs(ticket_id, created_at);
CREATE INDEX idx_state_logs_operator ON ticket_state_logs(operator_id);

-- ============================================================
-- 6. 催办记录
-- ============================================================

CREATE TABLE reminders (
    id              BIGSERIAL       PRIMARY KEY,
    ticket_id       BIGINT          NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    sender_id       BIGINT          NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    content         TEXT            NOT NULL,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_reminders_ticket ON reminders(ticket_id, created_at);

-- ============================================================
-- 7. SLA 策略
-- ============================================================

-- 每个 技能组+优先级 组合定义一套 SLA 时限
-- skill_group_id 为 NULL 表示全局默认
CREATE TABLE sla_policies (
    id                          BIGSERIAL       PRIMARY KEY,
    skill_group_id              BIGINT          REFERENCES skill_groups(id) ON DELETE CASCADE,
    priority                    VARCHAR(20)     NOT NULL,
    first_response_minutes      INT             NOT NULL,               -- 首次响应时限（分钟）
    solution_minutes            INT             NOT NULL,               -- 解决时限（分钟）
    created_at                  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    -- 每个技能组+优先级组合唯一；skill_group_id=NULL 时优先级全局唯一
    UNIQUE (skill_group_id, priority),

    CONSTRAINT chk_sla_priority CHECK (priority IN (
        'p1_urgent', 'p2_high', 'p3_normal', 'p4_enterprise'
    )),
    CONSTRAINT chk_sla_positive CHECK (
        first_response_minutes > 0 AND solution_minutes > 0
    )
);

-- ============================================================
-- 8. 钉钉通知记录
-- ============================================================

CREATE TABLE dingtalk_notifications (
    id              BIGSERIAL       PRIMARY KEY,
    ticket_id       BIGINT          NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    type            VARCHAR(30)     NOT NULL,               -- assigned / sla_warning / sla_breached / reminder / returned
    target_user_id  BIGINT          REFERENCES users(id) ON DELETE SET NULL,   -- 个人通知
    target_webhook  VARCHAR(500),                            -- 群通知 Webhook
    content         TEXT            NOT NULL,
    success         BOOLEAN         NOT NULL DEFAULT FALSE,
    error_message   TEXT,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_dingtalk_ticket ON dingtalk_notifications(ticket_id);
CREATE INDEX idx_dingtalk_user   ON dingtalk_notifications(target_user_id);

-- ============================================================
-- 9. 审计日志
-- ============================================================

CREATE TABLE audit_logs (
    id              BIGSERIAL       PRIMARY KEY,
    user_id         BIGINT          REFERENCES users(id) ON DELETE SET NULL,
    action          VARCHAR(50)     NOT NULL,               -- ticket.create / ticket.update / ticket.state_change / ...
    resource_type   VARCHAR(50)     NOT NULL,               -- ticket / user / group / ...
    resource_id     BIGINT,
    changes         JSONB,                                   -- 变更内容 {"field": {"old": x, "new": y}}
    ip_address      VARCHAR(45),
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_resource ON audit_logs(resource_type, resource_id);
CREATE INDEX idx_audit_user     ON audit_logs(user_id);
CREATE INDEX idx_audit_time     ON audit_logs(created_at DESC);

-- ============================================================
-- 种子数据
-- ============================================================

-- 客服组
INSERT INTO groups (id, name) VALUES
    (1, '客服一组');

-- 技能组
INSERT INTO skill_groups (id, name) VALUES
    (1, '技术组'),
    (2, '市场组'),
    (3, '售后组');

-- 管理员账户（密码: admin123，bcrypt hash）
INSERT INTO users (id, username, name, role, group_id, is_group_leader, password_hash) VALUES
    (1, 'admin', '系统管理员', 'admin', 1, FALSE, '$2b$12$Oxx10M2ohHR2zd3ekD5WLOll.icytUsKAjpzeoeTu3ZaYvpq0aRKW');

-- 一级分类
INSERT INTO ticket_categories (id, name, level, sort_order) VALUES
    (1,  '咨询',     1, 1),
    (2,  '报修',     1, 2),
    (3,  '投诉',     1, 3),
    (4,  '业务办理', 1, 4),
    (5,  '合作洽谈', 1, 5);

-- 二级分类（示例）
INSERT INTO ticket_categories (id, parent_id, name, level, sort_order) VALUES
    (101, 1, '产品咨询',     2, 1),
    (102, 1, '资费咨询',     2, 2),
    (103, 1, '使用指导',     2, 3),
    (201, 2, '设备故障',     2, 1),
    (202, 2, '网络故障',     2, 2),
    (203, 2, '信号问题',     2, 3),
    (301, 3, '服务态度投诉', 2, 1),
    (302, 3, '费用争议',     2, 2),
    (303, 3, '处理时效投诉', 2, 3),
    (401, 4, '套餐变更',     2, 1),
    (402, 4, '号码变更',     2, 2),
    (501, 5, '渠道合作',     2, 1),
    (502, 5, '产品合作',     2, 2);

-- SLA 默认策略（全局，不关联特定技能组）
INSERT INTO sla_policies (skill_group_id, priority, first_response_minutes, solution_minutes) VALUES
    (NULL, 'p1_urgent',     15, 120),    -- P1: 15分钟首次响应, 2小时解决
    (NULL, 'p2_high',       30, 240),    -- P2: 30分钟首次响应, 4小时解决
    (NULL, 'p3_normal',    120, 480),    -- P3: 2小时首次响应, 8小时解决
    (NULL, 'p4_enterprise', 10,  60);    -- P4: 10分钟首次响应, 1小时解决

-- 重置序列
SELECT setval('ticket_number_seq', 1, FALSE);
SELECT setval('groups_id_seq', (SELECT MAX(id) FROM groups));
SELECT setval('skill_groups_id_seq', (SELECT MAX(id) FROM skill_groups));
SELECT setval('users_id_seq', (SELECT MAX(id) FROM users));
SELECT setval('ticket_categories_id_seq', (SELECT MAX(id) FROM ticket_categories));
