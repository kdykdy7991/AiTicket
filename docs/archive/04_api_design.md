# 04 API 设计（API Design）

## 1. 通用约定

### 1.1 基础信息

| 项目 | 值 |
|---|---|
| Base URL | `/api/v1` |
| 数据格式 | JSON（`Content-Type: application/json`） |
| 认证方式 | `Authorization: Bearer <access_token>` |
| 时间格式 | ISO 8601（`2026-05-29T10:30:00+08:00`） |
| 字符编码 | UTF-8 |

### 1.2 分页

所有列表接口统一使用 `page` + `per_page` 参数：

**请求参数：**

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `page` | int | 1 | 页码（从 1 开始） |
| `per_page` | int | 25 | 每页数量（最大 100） |

**响应格式：**

```json
{
  "data": [...],
  "pagination": {
    "page": 1,
    "per_page": 25,
    "total": 156,
    "total_pages": 7
  }
}
```

### 1.3 排序

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `sort_by` | string | `created_at` | 排序字段 |
| `sort_order` | string | `desc` | `asc` 或 `desc` |

### 1.4 错误响应

所有错误返回统一格式：

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Ticket #1234 not found",
    "details": {}
  }
}
```

| HTTP 状态码 | error.code | 场景 |
|---|---|---|
| 400 | `BAD_REQUEST` | 请求参数不合法 |
| 401 | `UNAUTHORIZED` | 未认证或 token 过期 |
| 403 | `FORBIDDEN` | 无权限访问 |
| 404 | `NOT_FOUND` | 资源不存在 |
| 409 | `CONFLICT` | 资源冲突（如重复创建） |
| 422 | `VALIDATION_ERROR` | 参数校验失败（details 含字段级错误） |
| 429 | `RATE_LIMITED` | 触发限流 |
| 500 | `INTERNAL_ERROR` | 服务器内部错误 |

422 错误的 details 格式：

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Validation failed",
    "details": {
      "fields": [
        { "field": "email", "message": "Invalid email format" },
        { "field": "title", "message": "This field is required" }
      ]
    }
  }
}
```

---

## 2. 端点列表

### 2.1 认证（Auth）

| Method | Path | 权限 | 说明 | 需求编号 |
|---|---|---|---|---|
| POST | `/auth/login` | 公开 | 邮箱+密码登录 | F-AUTH-01 |
| POST | `/auth/refresh` | 公开（需 refresh_token） | 刷新 access_token | F-AUTH-02 |
| POST | `/auth/logout` | 已登录 | 登出（可选：加入 token 黑名单） | — |
| PUT | `/auth/password` | 已登录 | 修改自己的密码 | F-AUTH-04 |

**POST `/auth/login`**

```json
// Request
{ "email": "agent@example.com", "password": "secret123" }

// Response 200
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 1800,
  "user": {
    "id": 1,
    "email": "agent@example.com",
    "firstname": "张",
    "lastname": "三",
    "role": { "id": 2, "name": "agent" }
  }
}
```

**POST `/auth/refresh`**

```json
// Request
{ "refresh_token": "eyJ..." }

// Response 200
{ "access_token": "eyJ...", "expires_in": 1800 }
```

---

### 2.2 用户管理（Users）

| Method | Path | 权限 | 说明 | 需求编号 |
|---|---|---|---|---|
| GET | `/users` | admin | 用户列表（分页） | F-AUTH-03 |
| POST | `/users` | admin | 创建用户 | F-AUTH-03 |
| GET | `/users/{id}` | admin / self | 用户详情 | — |
| PUT | `/users/{id}` | admin | 更新用户 | F-AUTH-03 |
| DELETE | `/users/{id}` | admin | 禁用用户（软删除） | F-AUTH-03 |
| GET | `/users/me` | 已登录 | 当前用户信息 | — |

**POST `/users`**

```json
// Request
{
  "email": "new@example.com",
  "password": "initial123",
  "firstname": "李",
  "lastname": "四",
  "role_id": 2,
  "group_ids": [1, 3],
  "organization_id": 1
}

// Response 201
{
  "id": 5,
  "email": "new@example.com",
  "firstname": "李",
  "lastname": "四",
  "role": { "id": 2, "name": "agent" },
  "groups": [
    { "id": 1, "name": "技术支持组" },
    { "id": 3, "name": "VIP组" }
  ],
  "organization": { "id": 1, "name": "示例公司" },
  "active": true,
  "created_at": "2026-05-29T10:00:00+08:00"
}
```

---

### 2.3 角色（Roles）

| Method | Path | 权限 | 说明 |
|---|---|---|---|
| GET | `/roles` | admin | 角色列表 |
| GET | `/roles/{id}` | admin | 角色详情 |

MVP 阶段角色为预置数据，不提供创建/修改/删除接口。

---

### 2.4 客服组（Groups）

| Method | Path | 权限 | 说明 |
|---|---|---|---|
| GET | `/groups` | admin, agent | 组列表 |
| POST | `/groups` | admin | 创建组 |
| GET | `/groups/{id}` | admin, agent | 组详情（含成员列表） |
| PUT | `/groups/{id}` | admin | 更新组 |
| DELETE | `/groups/{id}` | admin | 禁用组 |

---

### 2.5 组织（Organizations）

| Method | Path | 权限 | 说明 |
|---|---|---|---|
| GET | `/organizations` | admin, agent | 组织列表 |
| POST | `/organizations` | admin | 创建组织 |
| GET | `/organizations/{id}` | admin, agent | 组织详情 |
| PUT | `/organizations/{id}` | admin | 更新组织 |
| DELETE | `/organizations/{id}` | admin | 禁用组织 |

---

### 2.6 工单（Tickets）

| Method | Path | 权限 | 说明 | 需求编号 |
|---|---|---|---|---|
| GET | `/tickets` | agent, customer | 工单列表（筛选+分页） | F-TKT-02 |
| POST | `/tickets` | agent, customer | 创建工单 | F-TKT-01 |
| GET | `/tickets/{id}` | agent(in group), customer(own) | 工单详情 | F-TKT-03 |
| PUT | `/tickets/{id}` | agent(in group) | 更新工单（状态/优先级/分配） | F-TKT-04/05/06 |
| POST | `/tickets/{id}/merge` | agent | 合并工单 | F-TKT-09 |

**筛选参数（GET `/tickets`）：**

| 参数 | 类型 | 说明 |
|---|---|---|
| `state_id` | int | 按状态筛选 |
| `priority_id` | int | 按优先级筛选 |
| `group_id` | int | 按组筛选 |
| `owner_id` | int | 按负责人筛选 |
| `customer_id` | int | 按客户筛选 |
| `channel` | string | 按渠道筛选 |
| `escalated` | bool | 仅显示已超时工单 |

**POST `/tickets`**

```json
// Request (Customer 创建)
{
  "title": "登录页面无法访问",
  "group_id": 1,
  "priority_id": 3,
  "article": {
    "body": "从今天上午 9 点开始，登录页面一直显示 502 错误...",
    "content_type": "text/plain"
  }
}

// Response 201
{
  "id": 42,
  "number": "TKT-00042",
  "title": "登录页面无法访问",
  "state": { "id": 1, "name": "new" },
  "priority": { "id": 3, "name": "high" },
  "group": { "id": 1, "name": "技术支持组" },
  "owner": null,
  "customer": { "id": 10, "firstname": "王", "lastname": "五" },
  "organization": { "id": 1, "name": "示例公司" },
  "channel": "web",
  "escalation_at": "2026-05-29T12:00:00+08:00",
  "article_count": 1,
  "created_at": "2026-05-29T10:00:00+08:00",
  "updated_at": "2026-05-29T10:00:00+08:00"
}
```

**PUT `/tickets/{id}`**

```json
// Request (Agent/Handler 更新)
{
  "state": "open",
  "owner_id": 5,
  "priority": "p2_high",
  "reason": "分派给张三处理"
}

// Response 200 — 返回更新后的完整工单对象
```

- `state` 使用后端字符串枚举：`pending` / `open` / `resolved` / `on_hold` / `callbacked` / `archived` / `returned` / `cancelled`
- `open→on_hold` 与 `callbacked→returned` 必须携带 `reason`
- `pending→open`（分派）必须携带 `owner_id`

**POST `/tickets/{id}/merge`**

```json
// Request
{ "target_ticket_id": 38 }

// Response 200 — 返回合并后的目标工单
```

---

### 2.7 对话条目（Articles）

| Method | Path | 权限 | 说明 | 需求编号 |
|---|---|---|---|---|
| GET | `/tickets/{ticket_id}/articles` | 同工单权限 | Article 列表 | F-TKT-03 |
| POST | `/tickets/{ticket_id}/articles` | agent, handler, customer(own ticket) | 追加 Article | F-TKT-07 |
| GET | `/tickets/{ticket_id}/articles/{id}` | 同工单权限 | Article 详情 | — |

**POST `/tickets/{ticket_id}/articles`**

```json
// Request (处理说明 / reply)：仅当前处理人可提交，提交后系统自动流转到 resolved
{
  "type": "reply",
  "body": "已确认是 Nginx 配置问题，已修复。"
}

// Request (追加 / addition)：仅 admin/agent 可提交，且工单状态须在 resolved 之前
{
  "type": "addition",
  "body": "补充一下当时的报错截图说明",
  "append_reason": "补充排查信息"
}

// Request (系统提醒 / reminder)
{
  "type": "reminder",
  "body": "距离 SLA 截止还有 30 分钟"
}

// Response 201
{
  "id": 101,
  "ticket_id": 42,
  "type": "reply",
  "sender_id": 5,
  "sender_name": "张三",
  "body": "已确认是 Nginx 配置问题，已修复。",
  "state_key": "resolved",
  "append_reason": null,
  "created_at": "2026-05-29T11:00:00+08:00"
}
```

- `type` 枚举：`reply` / `addition` / `reminder`（`internal_note` 已移除）
- `reply` 的 `state_key` 记录该处理说明归属的状态节点
- `addition` 必填 `append_reason`
- `reply` 在 `open`/`on_hold` 状态下由处理人提交时，后端自动将工单流转到 `resolved`

---

### 2.8 工单关联（Links）

| Method | Path | 权限 | 说明 | 需求编号 |
|---|---|---|---|---|
| GET | `/tickets/{ticket_id}/links` | agent | 获取关联列表 | F-TKT-08 |
| POST | `/tickets/{ticket_id}/links` | agent | 创建关联 | F-TKT-08 |
| DELETE | `/tickets/{ticket_id}/links/{id}` | agent | 删除关联 | — |

**POST `/tickets/{ticket_id}/links`**

```json
// Request
{ "target_ticket_id": 38, "link_type": "related" }

// Response 201
{
  "id": 5,
  "source_ticket": { "id": 42, "number": "TKT-00042", "title": "登录页面无法访问" },
  "target_ticket": { "id": 38, "number": "TKT-00038", "title": "502 错误排查" },
  "link_type": "related",
  "created_at": "2026-05-29T11:30:00+08:00"
}
```

---

### 2.9 SLA 策略（SLA Policies）

| Method | Path | 权限 | 说明 | 需求编号 |
|---|---|---|---|---|
| GET | `/sla-policies` | admin | 策略列表 | F-SLA-01 |
| POST | `/sla-policies` | admin | 创建策略 | F-SLA-01 |
| GET | `/sla-policies/{id}` | admin | 策略详情 | — |
| PUT | `/sla-policies/{id}` | admin | 更新策略 | — |
| DELETE | `/sla-policies/{id}` | admin | 删除策略 | — |

**POST `/sla-policies`**

```json
// Request
{
  "name": "VIP 高优先级 SLA",
  "group_id": 3,
  "priority_id": 4,
  "first_response_time": 30,
  "update_time": 120,
  "solution_time": 240,
  "calendar_id": 1
}
```

---

### 2.10 日历（Calendars）

| Method | Path | 权限 | 说明 |
|---|---|---|---|
| GET | `/calendars` | admin | 日历列表 |
| POST | `/calendars` | admin | 创建日历 |
| GET | `/calendars/{id}` | admin | 日历详情 |
| PUT | `/calendars/{id}` | admin | 更新日历 |
| DELETE | `/calendars/{id}` | admin | 删除日历 |

---

### 2.11 触发器（Triggers）

| Method | Path | 权限 | 说明 | 需求编号 |
|---|---|---|---|---|
| GET | `/triggers` | admin | 触发器列表 | F-TRG-01 |
| POST | `/triggers` | admin | 创建触发器 | F-TRG-01 |
| GET | `/triggers/{id}` | admin | 触发器详情 | — |
| PUT | `/triggers/{id}` | admin | 更新触发器 | — |
| DELETE | `/triggers/{id}` | admin | 删除触发器 | — |

**POST `/triggers`**

```json
// Request
{
  "name": "新工单自动分配到技术支持组",
  "conditions": {
    "all": [
      { "field": "ticket.state_id", "operator": "is", "value": 1 }
    ]
  },
  "actions": [
    { "action": "set_group", "value": 1 },
    { "action": "send_email", "value": { "recipient": "group_agents", "template": "new_ticket" } }
  ],
  "execution_order": 10,
  "active": true
}
```

---

### 2.12 工单视图（Overviews）

| Method | Path | 权限 | 说明 | 需求编号 |
|---|---|---|---|---|
| GET | `/overviews` | agent, admin | 可用视图列表 | F-OV-01 |
| POST | `/overviews` | admin | 创建视图 | F-OV-02 |
| GET | `/overviews/{id}` | agent, admin | 视图详情 | — |
| PUT | `/overviews/{id}` | admin | 更新视图 | — |
| DELETE | `/overviews/{id}` | admin | 删除视图 | — |
| GET | `/overviews/{id}/tickets` | agent, admin | 执行视图查询（返回工单列表） | F-OV-01 |

**GET `/overviews/{id}/tickets`**

返回格式与 `GET /tickets` 相同（分页工单列表），但查询条件由 Overview 的 `conditions` 决定。

---

### 2.13 邮件渠道（Email Channels）

| Method | Path | 权限 | 说明 | 需求编号 |
|---|---|---|---|---|
| GET | `/channels/email` | admin | 邮件渠道列表 | F-EM-01 |
| POST | `/channels/email` | admin | 创建邮件渠道 | F-EM-01 |
| GET | `/channels/email/{id}` | admin | 渠道详情 | — |
| PUT | `/channels/email/{id}` | admin | 更新渠道 | — |
| DELETE | `/channels/email/{id}` | admin | 删除渠道 | — |
| POST | `/channels/email/{id}/test` | admin | 测试连接（IMAP+SMTP） | — |

---

### 2.14 搜索（Search）

| Method | Path | 权限 | 说明 | 需求编号 |
|---|---|---|---|---|
| GET | `/search` | agent, customer | 全文检索 | F-SR-01 |

**GET `/search?q=登录失败&type=ticket`**

```json
{
  "data": [
    {
      "type": "ticket",
      "id": 42,
      "number": "TKT-00042",
      "title": "登录页面无法访问",
      "state": { "id": 2, "name": "open" },
      "highlight": "...从今天上午 9 点开始，<em>登录</em>页面一直显示 502 错误...",
      "score": 0.85
    }
  ],
  "pagination": { "page": 1, "per_page": 25, "total": 3, "total_pages": 1 }
}
```

---

### 2.15 统计（Stats）

| Method | Path | 权限 | 说明 |
|---|---|---|---|
| GET | `/stats/dashboard` | agent, admin | 仪表盘统计数据 |

```json
// Response
{
  "tickets_by_state": [
    { "state": "new", "count": 12 },
    { "state": "open", "count": 34 },
    { "state": "pending", "count": 8 }
  ],
  "tickets_by_priority": [
    { "priority": "urgent", "count": 5 },
    { "priority": "high", "count": 15 }
  ],
  "escalated_count": 3,
  "avg_first_response_minutes": 45,
  "avg_resolution_minutes": 480,
  "created_today": 8,
  "resolved_today": 6
}
```

---

### 2.16 健康检查（Health）

| Method | Path | 权限 | 说明 |
|---|---|---|---|
| GET | `/healthz` | 公开 | 存活检查（返回 200） |
| GET | `/readyz` | 公开 | 就绪检查（DB + Redis 连通性） |

```json
// GET /readyz Response 200
{
  "status": "ok",
  "checks": {
    "database": "ok",
    "redis": "ok"
  }
}
```

---

## 3. 权限矩阵

| 端点 | Admin | Agent | Handler | Customer | 公开 |
|---|---|---|---|---|---|
| `POST /auth/login` | — | — | — | — | **Y** |
| `POST /auth/refresh` | — | — | — | — | **Y** |
| `PUT /auth/password` | **Y** | **Y** | **Y** | **Y** | |
| `GET /users` | **Y** | | | | |
| `POST /users` | **Y** | | | | |
| `GET /users/{id}` | **Y** | | | self | |
| `PUT /users/{id}` | **Y** | | | | |
| `GET /users/me` | **Y** | **Y** | **Y** | **Y** | |
| `GET /roles` | **Y** | | | | |
| `* /groups` | **Y** | R | R | | |
| `* /organizations` | **Y** | R | R | | |
| `GET /tickets` | **Y** | group | group | own | |
| `POST /tickets` | **Y** | **Y** | **Y** | **Y** | |
| `GET /tickets/{id}` | **Y** | group | group | own | |
| `PUT /tickets/{id}` | **Y** | owner/dispatch | dispatch | | |
| `POST /tickets/{id}/merge` | **Y** | group | | | |
| `* /tickets/{id}/articles` | **Y** | group | group | own(R+C) | |
| `* /tickets/{id}/links` | **Y** | group | | | |
| `* /sla-policies` | **Y** | | | | |
| `* /calendars` | **Y** | | | |
| `* /triggers` | **Y** | | | |
| `GET /overviews` | **Y** | **Y** | | |
| `POST/PUT/DELETE /overviews` | **Y** | | | |
| `GET /overviews/{id}/tickets` | **Y** | **Y** | | |
| `* /channels/email` | **Y** | | | |
| `GET /search` | **Y** | group | own | |
| `GET /stats/dashboard` | **Y** | **Y** | | |
| `GET /healthz` | — | — | — | **Y** |
| `GET /readyz` | — | — | — | **Y** |

**图例：**
- **Y** = 完整访问
- **R** = 只读
- **group** = 仅限所在 Group 的数据
- **own** = 仅限自己创建的数据
- **R+C** = 只读 + 创建（不可修改/删除）
- **self** = 仅限访问自己的记录
