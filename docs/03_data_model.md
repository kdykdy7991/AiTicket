# 03 数据模型（Data Model）

## 1. ER 关系图

```
┌──────────────┐       ┌──────────────┐       ┌──────────────────┐
│    roles     │       │organizations │       │    calendars     │
│──────────────│       │──────────────│       │──────────────────│
│ id (PK)      │       │ id (PK)      │       │ id (PK)          │
│ name         │       │ name         │       │ name             │
│ permissions  │       │ domain       │       │ timezone         │
│ is_default   │       │ active       │       │ business_hours   │
└──────┬───────┘       └──────┬───────┘       │ holidays         │
       │ 1                    │ 1             └────────┬─────────┘
       │                      │                        │ 1
       │ N                    │ N                      │
┌──────┴───────┐       ┌──────┴───────┐       ┌───────┴──────────┐
│    users     │       │              │       │   sla_policies   │
│──────────────│       │              │       │──────────────────│
│ id (PK)      │       │              │       │ id (PK)          │
│ email        ├───┐   │              │       │ name             │
│ password_hash│   │   │              │       │ group_id (FK)    │
│ firstname    │   │   │              │       │ priority_id (FK) │
│ lastname     │   │   │              │       │ first_response   │
│ role_id (FK) │   │   │              │       │ update_time      │
│ org_id (FK)  │   │   │              │       │ solution_time    │
│ active       │   │   │              │       │ calendar_id (FK) │
└──┬───┬───────┘   │   │              │       └──────────────────┘
   │   │           │   │              │
   │   │ M:N       │   │              │
   │   │           │   │              │
   │ ┌─┴────────┐  │   │              │
   │ │user_groups│  │   │              │
   │ │──────────│  │   │              │
   │ │user_id   │  │   │              │
   │ │group_id  │  │   │              │
   │ └─┬────────┘  │   │              │
   │   │           │   │              │
   │   │ N         │   │              │
   │ ┌─┴────────┐  │   │              │
   │ │  groups   │  │   │              │
   │ │──────────│  │   │              │
   │ │ id (PK)  │  │   │              │
   │ │ name     │  │   │              │
   │ │ parent_id│  │   │              │
   │ └─┬────────┘  │   │              │
   │   │           │   │              │
   │   │           │   │              │
   │   │ 1     1   │   │              │
   │   ▼       ▼   │   │              │
   │ ┌─────────────┴───┴──────────────┤
   │ │          tickets               │
   │ │────────────────────────────────│
   │ │ id (PK)        number (UQ)    │
   │ │ title          state_id (FK)  │
   │ │ priority_id    group_id (FK)  │
   │ │ owner_id (FK)  customer_id    │
   │ │ org_id (FK)    channel        │
   │ │ escalation_at  first_resp_at  │
   │ │ close_at       created_at     │
   │ └──────┬─────────┬──────────────┘
   │        │ 1       │ 1
   │        │         │
   │        │ N       │ N
   │  ┌─────┴────┐  ┌─┴──────────┐
   │  │ articles  │  │ticket_links│
   │  │──────────│  │────────────│
   │  │ id (PK)  │  │ id (PK)    │
   │  │ticket_id │  │ source_id  │
   │  │sender    │  │ target_id  │
   │  │type      │  │ link_type  │
   │  │body      │  └────────────┘
   │  │internal  │
   │  └──────────┘
   │
   │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
   │  │   triggers   │  │  overviews   │  │email_channels│
   │  │──────────────│  │──────────────│  │──────────────│
   │  │ id (PK)      │  │ id (PK)      │  │ id (PK)      │
   │  │ name         │  │ name         │  │ name         │
   │  │ conditions   │  │ conditions   │  │ group_id(FK) │
   │  │ actions      │  │ order_by     │  │ imap_*       │
   │  │ exec_order   │  │ role_ids     │  │ smtp_*       │
   │  └──────────────┘  └──────────────┘  └──────────────┘
   │
   └──→ ┌──────────────┐
        │  audit_logs  │
        │──────────────│
        │ id (PK)      │
        │ user_id (FK) │
        │ action       │
        │ record_type  │
        │ record_id    │
        │ changes      │
        └──────────────┘
```

## 2. 表定义

### 2.1 roles（角色）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | SERIAL | PK | |
| `name` | VARCHAR(50) | UNIQUE, NOT NULL | admin / agent / customer |
| `permissions` | JSONB | NOT NULL, DEFAULT '[]' | 权限列表，如 `["ticket.agent", "admin.user"]` |
| `is_default` | BOOLEAN | DEFAULT false | 新用户默认角色（仅一个为 true） |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

### 2.2 organizations（组织）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | SERIAL | PK | |
| `name` | VARCHAR(150) | NOT NULL | 组织名称 |
| `domain` | VARCHAR(250) | | 邮件域名，用于自动关联 |
| `note` | TEXT | | 备注 |
| `active` | BOOLEAN | DEFAULT true | |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

### 2.3 users（用户）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | SERIAL | PK | |
| `email` | VARCHAR(255) | UNIQUE, NOT NULL | 登录邮箱 |
| `password_hash` | VARCHAR(255) | NOT NULL | bcrypt hash |
| `firstname` | VARCHAR(100) | | |
| `lastname` | VARCHAR(100) | | |
| `phone` | VARCHAR(50) | | |
| `role_id` | INTEGER | FK → roles.id, NOT NULL | 用户角色（一对多） |
| `organization_id` | INTEGER | FK → organizations.id, NULL | 所属组织 |
| `active` | BOOLEAN | DEFAULT true | 是否启用 |
| `last_login` | TIMESTAMPTZ | | 最后登录时间 |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

**索引：**
- `ix_users_email` UNIQUE on `email`
- `ix_users_role_id` on `role_id`
- `ix_users_organization_id` on `organization_id`

### 2.4 groups（客服组）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | SERIAL | PK | |
| `name` | VARCHAR(150) | NOT NULL | 组名称 |
| `parent_id` | INTEGER | FK → groups.id, NULL | 父组（树状嵌套） |
| `note` | TEXT | | 备注 |
| `active` | BOOLEAN | DEFAULT true | |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

### 2.5 user_groups（用户-组关联）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `user_id` | INTEGER | FK → users.id, NOT NULL | |
| `group_id` | INTEGER | FK → groups.id, NOT NULL | |

**约束：** PRIMARY KEY (`user_id`, `group_id`)

### 2.6 ticket_states（工单状态）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | SERIAL | PK | |
| `name` | VARCHAR(50) | UNIQUE, NOT NULL | 状态名称 |
| `state_type` | VARCHAR(20) | NOT NULL | 分类：new / open / pending / closed / merged |
| `default_create` | BOOLEAN | DEFAULT false | 新建工单默认状态 |
| `default_follow_up` | BOOLEAN | DEFAULT false | 客户跟进时的默认状态 |
| `active` | BOOLEAN | DEFAULT true | |

### 2.7 ticket_priorities（工单优先级）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | SERIAL | PK | |
| `name` | VARCHAR(50) | UNIQUE, NOT NULL | 优先级名称 |
| `ui_color` | VARCHAR(20) | | 前端显示颜色 |
| `ui_icon` | VARCHAR(50) | | 前端图标 |
| `default_create` | BOOLEAN | DEFAULT false | 新建工单默认优先级 |
| `sort_order` | INTEGER | DEFAULT 0 | 排序权重 |
| `active` | BOOLEAN | DEFAULT true | |

### 2.8 tickets（工单）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | SERIAL | PK | |
| `number` | VARCHAR(20) | UNIQUE, NOT NULL | 工单编号，如 "TKT-00001" |
| `title` | VARCHAR(500) | NOT NULL | 工单标题 |
| `state_id` | INTEGER | FK → ticket_states.id, NOT NULL | 当前状态 |
| `priority_id` | INTEGER | FK → ticket_priorities.id, NOT NULL | 优先级 |
| `group_id` | INTEGER | FK → groups.id, NOT NULL | 所属客服组 |
| `owner_id` | INTEGER | FK → users.id, NULL | 负责的客服（可为空=未分配） |
| `customer_id` | INTEGER | FK → users.id, NOT NULL | 提交者 |
| `organization_id` | INTEGER | FK → organizations.id, NULL | 关联组织 |
| `channel` | VARCHAR(20) | NOT NULL, DEFAULT 'web' | 来源渠道：web / email |
| `escalation_at` | TIMESTAMPTZ | | SLA 升级时间点 |
| `first_response_at` | TIMESTAMPTZ | | 首次响应时间 |
| `close_at` | TIMESTAMPTZ | | 关闭时间 |
| `last_contact_agent_at` | TIMESTAMPTZ | | 最后一次客服回复时间 |
| `last_contact_customer_at` | TIMESTAMPTZ | | 最后一次客户回复时间 |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

**索引：**
- `ix_tickets_number` UNIQUE on `number`
- `ix_tickets_state_group` on `(group_id, state_id)` — 列表查询主索引
- `ix_tickets_owner` on `(owner_id, state_id)` — "我的待处理"查询
- `ix_tickets_customer` on `(customer_id)` — 客户查看自己的工单
- `ix_tickets_escalation` on `(escalation_at)` WHERE `escalation_at IS NOT NULL` — SLA 检查
- `ix_tickets_created` on `(created_at DESC)` — 按时间排序
- `ix_tickets_fulltext` GIN on `to_tsvector('simple', title)` — 全文检索

### 2.9 articles（对话条目）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | BIGSERIAL | PK | |
| `ticket_id` | BIGINT | FK → tickets.id, NOT NULL | 所属工单 |
| `sender_id` | BIGINT | FK → users.id, NOT NULL | 创建者 |
| `type` | VARCHAR(20) | NOT NULL | reply / addition / reminder |
| `body` | TEXT | NOT NULL | 正文内容 |
| `state_key` | VARCHAR(30) | | 处理说明归属的状态节点（如 `resolved`） |
| `append_reason` | TEXT | | 追加原因（type='addition' 时必填） |
| `subject` | VARCHAR(500) | | 主题（邮件场景，可选） |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

**索引：**
- `ix_articles_ticket` on `(ticket_id, created_at)` — 按时间线查看
- `ix_articles_ticket_state` on `(ticket_id, state_key)` — 状态节点挂载处理说明

### 2.10 ticket_links（工单关联）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | SERIAL | PK | |
| `source_ticket_id` | INTEGER | FK → tickets.id, NOT NULL | 源工单 |
| `target_ticket_id` | INTEGER | FK → tickets.id, NOT NULL | 目标工单 |
| `link_type` | VARCHAR(20) | NOT NULL | parent / child / related |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

**约束：**
- UNIQUE (`source_ticket_id`, `target_ticket_id`, `link_type`)
- CHECK (`source_ticket_id != target_ticket_id`)

### 2.11 sla_policies（SLA 策略）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | SERIAL | PK | |
| `name` | VARCHAR(150) | NOT NULL | 策略名称 |
| `group_id` | INTEGER | FK → groups.id, NULL | 适用组（NULL = 全部组） |
| `priority_id` | INTEGER | FK → ticket_priorities.id, NULL | 适用优先级（NULL = 全部） |
| `first_response_time` | INTEGER | | 首次响应时限（分钟） |
| `update_time` | INTEGER | | 更新时限（分钟） |
| `solution_time` | INTEGER | | 解决时限（分钟） |
| `calendar_id` | INTEGER | FK → calendars.id, NULL | 关联日历（NULL = 7×24） |
| `active` | BOOLEAN | DEFAULT true | |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

**匹配优先级：** group_id + priority_id 精确匹配 > group_id 匹配 > 全局默认

### 2.12 calendars（工作日历）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | SERIAL | PK | |
| `name` | VARCHAR(150) | NOT NULL | |
| `timezone` | VARCHAR(50) | NOT NULL, DEFAULT 'Asia/Shanghai' | |
| `business_hours` | JSONB | NOT NULL | 工作时段定义（见 §3.1） |
| `holidays` | JSONB | DEFAULT '[]' | 节假日列表（见 §3.2） |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

### 2.13 triggers（触发器）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | SERIAL | PK | |
| `name` | VARCHAR(150) | NOT NULL | 触发器名称 |
| `conditions` | JSONB | NOT NULL | 匹配条件（见 §3.3） |
| `actions` | JSONB | NOT NULL | 执行动作（见 §3.4） |
| `active` | BOOLEAN | DEFAULT true | |
| `execution_order` | INTEGER | DEFAULT 0 | 执行顺序（升序） |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

### 2.14 overviews（工单视图）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | SERIAL | PK | |
| `name` | VARCHAR(150) | NOT NULL | 视图名称 |
| `conditions` | JSONB | NOT NULL | 查询条件（见 §3.5） |
| `order_by` | VARCHAR(50) | DEFAULT 'created_at' | 排序字段 |
| `order_direction` | VARCHAR(4) | DEFAULT 'desc' | asc / desc |
| `prio` | INTEGER | DEFAULT 0 | 显示排序权重 |
| `role_ids` | JSONB | DEFAULT '[]' | 可见角色 ID 列表 |
| `active` | BOOLEAN | DEFAULT true | |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

### 2.15 email_channels（邮件渠道）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | SERIAL | PK | |
| `name` | VARCHAR(150) | NOT NULL | 渠道名称 |
| `group_id` | INTEGER | FK → groups.id, NOT NULL | 绑定的客服组 |
| `imap_host` | VARCHAR(255) | NOT NULL | |
| `imap_port` | INTEGER | DEFAULT 993 | |
| `imap_ssl` | BOOLEAN | DEFAULT true | |
| `imap_user` | VARCHAR(255) | NOT NULL | |
| `imap_password` | VARCHAR(500) | NOT NULL | 加密存储 |
| `smtp_host` | VARCHAR(255) | NOT NULL | |
| `smtp_port` | INTEGER | DEFAULT 587 | |
| `smtp_ssl` | BOOLEAN | DEFAULT true | |
| `smtp_user` | VARCHAR(255) | NOT NULL | |
| `smtp_password` | VARCHAR(500) | NOT NULL | 加密存储 |
| `active` | BOOLEAN | DEFAULT true | |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

### 2.16 audit_logs（审计日志）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | BIGSERIAL | PK | 大量写入用 BIGSERIAL |
| `user_id` | INTEGER | FK → users.id, NULL | 操作人（系统操作为 NULL） |
| `action` | VARCHAR(50) | NOT NULL | create / update / delete / login / logout |
| `record_type` | VARCHAR(50) | NOT NULL | 目标类型：ticket / article / user / ... |
| `record_id` | INTEGER | | 目标记录 ID |
| `changes` | JSONB | | 变更详情 `{"field": {"from": old, "to": new}}` |
| `ip_address` | VARCHAR(45) | | 请求 IP |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

**索引：**
- `ix_audit_logs_record` on `(record_type, record_id)` — 按对象查审计
- `ix_audit_logs_user` on `(user_id, created_at DESC)` — 按用户查审计
- `ix_audit_logs_created` on `(created_at)` — 按时间范围查

## 3. JSONB 字段内部结构

### 3.1 Calendar.business_hours

```json
{
  "monday":    { "active": true,  "start": "09:00", "end": "18:00" },
  "tuesday":   { "active": true,  "start": "09:00", "end": "18:00" },
  "wednesday": { "active": true,  "start": "09:00", "end": "18:00" },
  "thursday":  { "active": true,  "start": "09:00", "end": "18:00" },
  "friday":    { "active": true,  "start": "09:00", "end": "17:00" },
  "saturday":  { "active": false },
  "sunday":    { "active": false }
}
```

### 3.2 Calendar.holidays

```json
[
  { "date": "2026-01-01", "name": "元旦" },
  { "date": "2026-01-28", "name": "春节" }
]
```

### 3.3 Trigger.conditions

条件组之间是 AND 关系，每个条件包含 `field`、`operator`、`value`：

```json
{
  "all": [
    { "field": "ticket.state_id",    "operator": "is",       "value": 1 },
    { "field": "ticket.priority_id", "operator": "is",       "value": 4 },
    { "field": "ticket.group_id",    "operator": "is",       "value": 2 }
  ],
  "any": [
    { "field": "article.body",       "operator": "contains", "value": "紧急" },
    { "field": "ticket.title",       "operator": "contains", "value": "故障" }
  ]
}
```

**支持的 operator：**
- `is` / `is_not` — 精确匹配
- `contains` / `not_contains` — 文本包含
- `starts_with` / `ends_with` — 前缀/后缀
- `is_set` / `not_set` — 是否有值
- `before` / `after` — 时间比较（用于 created_at 等）

### 3.4 Trigger.actions

```json
[
  { "action": "set_group",    "value": 3 },
  { "action": "set_owner",    "value": 12 },
  { "action": "set_state",    "value": 2 },
  { "action": "set_priority", "value": 4 },
  { "action": "send_email",   "value": { "recipient": "owner", "template": "trigger_notify" } }
]
```

**支持的 action：**
- `set_group` — 变更所属组
- `set_owner` — 分配负责人
- `set_state` — 变更状态
- `set_priority` — 变更优先级
- `send_email` — 发送通知邮件（recipient: owner / customer / group_agents）

### 3.5 Overview.conditions

与 Trigger.conditions 格式相同，但只支持 `all`（AND）：

```json
{
  "all": [
    { "field": "ticket.state_id",  "operator": "is_not", "value": 5 },
    { "field": "ticket.owner_id",  "operator": "is",     "value": "current_user" },
    { "field": "ticket.group_id",  "operator": "is",     "value": "current_user_groups" }
  ]
}
```

特殊值：
- `"current_user"` — 运行时替换为当前登录用户 ID
- `"current_user_groups"` — 运行时替换为当前用户所在的 group_id 列表（IN 查询）

### 3.6 AuditLog.changes

```json
{
  "state_id": { "from": 1, "to": 2 },
  "owner_id": { "from": null, "to": 5 },
  "priority_id": { "from": 2, "to": 4 }
}
```

## 4. 索引策略总结

| 表 | 索引 | 类型 | 覆盖场景 |
|---|---|---|---|
| tickets | `(group_id, state_id)` | B-tree | 列表按组+状态筛选 |
| tickets | `(owner_id, state_id)` | B-tree | "我的待处理"视图 |
| tickets | `(customer_id)` | B-tree | 客户查看自己的工单 |
| tickets | `(escalation_at)` partial | B-tree | SLA 超时扫描 |
| tickets | `(created_at DESC)` | B-tree | 按时间排序 |
| tickets | `to_tsvector(title)` | GIN | 标题全文检索 |
| articles | `(ticket_id, created_at)` | B-tree | 工单详情 Article 时间线 |
| articles | `to_tsvector(body)` | GIN | 正文全文检索 |
| audit_logs | `(record_type, record_id)` | B-tree | 对象审计查询 |
| audit_logs | `(user_id, created_at DESC)` | B-tree | 用户操作记录 |
| users | `(email)` | B-tree, UNIQUE | 登录查询 |

## 5. 种子数据（Seed Data）

### 5.1 默认角色

| name | permissions | is_default |
|---|---|---|
| admin | `["admin.*", "ticket.*"]` | false |
| agent | `["ticket.agent", "ticket.read", "ticket.write"]` | false |
| customer | `["ticket.customer"]` | true |

### 5.2 默认工单状态

| name | state_type | default_create | default_follow_up |
|---|---|---|---|
| new | new | true | false |
| open | open | false | true |
| pending | pending | false | false |
| resolved | closed | false | false |
| closed | closed | false | false |
| merged | merged | false | false |

### 5.3 默认工单优先级

| name | ui_color | sort_order | default_create |
|---|---|---|---|
| low | #38bdf8 | 1 | false |
| normal | #22c55e | 2 | true |
| high | #f59e0b | 3 | false |
| urgent | #ef4444 | 4 | false |

### 5.4 默认日历

| name | timezone | business_hours |
|---|---|---|
| 默认日历 | Asia/Shanghai | 周一至周五 09:00-18:00 |

### 5.5 默认 Overview

| name | conditions | 可见角色 |
|---|---|---|
| 我的待处理 | owner=current_user, state≠closed | agent |
| 组内未分配 | group=current_user_groups, owner=null, state=new | agent |
| 逾期工单 | escalation_at < now, state≠closed | agent, admin |
| 所有工单 | (无额外条件) | admin |

## 6. 状态机流转规则

```
         ┌──────────────────────────────┐
         │                              │
         ▼                              │
       [new] ──→ [open] ──→ [pending] ──┘
         │         │            │
         │         │            │
         │         ▼            │
         │     [resolved] ◄────┘
         │         │
         │         ▼
         └──→ [closed]
         
         任意状态 ──→ [merged]（仅合并操作）
```

**合法转换：**

| 当前状态 | 可转换到 |
|---|---|
| new | open, closed, merged |
| open | pending, resolved, closed, merged |
| pending | open, resolved, closed, merged |
| resolved | open, closed |
| closed | open（重新打开） |
| merged | （不可变更） |
