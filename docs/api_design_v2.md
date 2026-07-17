# Skdy 工单系统一期 — API 接口文档

> 版本：1.0
> 日期：2026-06-16
> 基线：PRD-工单系统一期.md

---

## 通用约定

### Base URL

```
/api/v1
```

### 认证

所有接口（登录除外）需在 Header 携带：

```
Authorization: Bearer <access_token>
```

### 时间格式

- 请求/响应统一使用 ISO 8601：`2026-06-16T15:30:00+08:00`
- 数据库存储 UTC，API 返回带时区

### 分页

请求参数：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| page | int | 1 | 页码（从 1 开始） |
| page_size | int | 20 | 每页条数（最大 100） |

响应格式：

```json
{
  "data": [...],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 156,
    "total_pages": 8
  }
}
```

### 错误响应

```json
{
  "error": {
    "code": "TICKET_NOT_FOUND",
    "message": "工单不存在",
    "details": null
  }
}
```

HTTP 状态码：

| 状态码 | 含义 |
|--------|------|
| 400 | 请求参数错误 |
| 401 | 未认证 / Token 过期 |
| 403 | 无权限 |
| 404 | 资源不存在 |
| 409 | 冲突（如重复创建） |
| 422 | 字段校验失败 |
| 500 | 服务器内部错误 |

### 字段校验错误（422）

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "字段校验失败",
    "details": [
      {"field": "customer_phone", "message": "请输入联系电话"},
      {"field": "priority", "message": "无效的优先级"}
    ]
  }
}
```

---

## 1. 认证

### POST /auth/login

登录获取 Token。

**请求：**

```json
{
  "username": "admin",
  "password": "admin123"
}
```

**响应：**

```json
{
  "data": {
    "access_token": "eyJ...",
    "refresh_token": "eyJ...",
    "token_type": "bearer",
    "expires_in": 1800,
    "user": {
      "id": 1,
      "username": "admin",
      "name": "系统管理员",
      "role": "admin",
      "group_id": 1,
      "is_group_leader": false
    }
  }
}
```

### POST /auth/refresh

刷新 Token。

**请求：**

```json
{
  "refresh_token": "eyJ..."
}
```

**响应：** 同 login

### POST /auth/logout

登出（使方 Token 失效）。

**权限：** 已认证用户

---

## 2. 用户

### GET /users

获取用户列表。

**权限：** admin

**查询参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| role | string | 按角色筛选：admin / agent / handler |
| group_id | int | 按客服组筛选 |
| skill_group_id | int | 按技能组筛选 |
| is_active | bool | 按状态筛选 |
| keyword | string | 搜索姓名/用户名 |

### GET /users/{id}

获取用户详情。

**权限：** admin 或本人

### POST /users

创建用户。

**权限：** admin

**请求：**

```json
{
  "username": "agent01",
  "name": "张三",
  "phone": "13800138001",
  "password": "Pass1234",
  "role": "agent",
  "group_id": 1,
  "is_group_leader": false,
  "skill_group_ids": [1],
  "dingtalk_id": "dingtalk_user_id_xxx"
}
```

### PATCH /users/{id}

更新用户信息。

**权限：** admin 或本人（仅可改 name/phone/password）

### DELETE /users/{id}

软删除（设置 is_active=false）。

**权限：** admin

---

## 3. 客服组

### GET /groups

获取客服组列表。

**权限：** 已认证用户

### POST /groups

创建客服组。

**权限：** admin

**请求：**

```json
{
  "name": "客服二组",
  "dingtalk_webhook_url": "https://oapi.dingtalk.com/robot/send?access_token=xxx"
}
```

### PATCH /groups/{id}

更新客服组。

**权限：** admin

### DELETE /groups/{id}

删除客服组（有用户关联时拒绝）。

**权限：** admin

---

## 4. 技能组

### GET /skill-groups

获取技能组列表。

**权限：** 已认证用户

### POST /skill-groups

创建技能组。

**权限：** admin

**请求：**

```json
{
  "name": "运维组",
  "dingtalk_webhook_url": "https://oapi.dingtalk.com/robot/send?access_token=xxx"
}
```

### PATCH /skill-groups/{id}

更新技能组。

**权限：** admin

### DELETE /skill-groups/{id}

删除技能组（有关联工单时拒绝）。

**权限：** admin

---

## 5. 工单

### GET /tickets

查询工单列表。

**权限：** admin 见全部；agent 见本组 + 自己受理的；handler 见派给自己的

**查询参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| state | string[] | 按状态筛选（多选，逗号分隔） |
| priority | string[] | 按优先级筛选 |
| skill_group_id | int | 按技能组筛选 |
| owner_id | int | 按负责人筛选 |
| group_id | int | 按客服组筛选 |
| category_id | int | 按分类筛选 |
| customer_type | string | 按客户类型筛选：personal / enterprise |
| channel | string | 按渠道筛选 |
| is_duplicate | bool | 是否重投工单 |
| is_overdue | bool | 是否超时 |
| created_from | date | 创建时间起（含） |
| created_to | date | 创建时间止（含） |
| closed_from | date | 结案时间起 |
| closed_to | date | 结案时间止 |
| keyword | string | 模糊匹配标题/描述 |
| sort | string | 排序：created_desc（默认）/ created_asc / priority_asc / sla_asc |
| page | int | 页码 |
| page_size | int | 每页条数 |

**响应：**

```json
{
  "data": [
    {
      "id": 1,
      "number": "TKT-00001",
      "title": "设备故障-无法开机",
      "state": "open",
      "priority": "p2_high",
      "channel": "phone",
      "customer_type": "personal",
      "customer_name": "李四",
      "customer_phone": "138****8001",
      "skill_group_id": 1,
      "skill_group_name": "技术组",
      "owner_id": 2,
      "owner_name": "张三",
      "category_id": 201,
      "category_name": "设备故障",
      "is_duplicate": false,
      "sla_first_response_breached": false,
      "sla_solution_breached": false,
      "first_response_deadline": "2026-06-16T16:00:00+08:00",
      "solution_deadline": "2026-06-16T19:30:00+08:00",
      "created_at": "2026-06-16T15:30:00+08:00",
      "updated_at": "2026-06-16T15:35:00+08:00"
    }
  ],
  "pagination": { "page": 1, "page_size": 20, "total": 1, "total_pages": 1 }
}
```

### GET /tickets/{id}

获取工单详情（含客户信息、分类、SLA、最新 article 等）。

**权限：** admin 全量；agent 本组 + 自己受理的；handler 派给自己的

### POST /tickets

创建工单。

**权限：** agent / admin

**请求：**

```json
{
  "title": "设备故障-无法开机",
  "description": "客户反馈终端设备无法开机，电源指示灯不亮",
  "priority": "p2_high",
  "channel": "phone",
  "customer_type": "personal",
  "customer_name": "李四",
  "customer_phone": "13800138001",
  "customer_company": "XX公司",
  "customer_level": "normal",
  "device_sn": "SN-2024-00123",
  "region_id": 110101,
  "category_id": 201,
  "symptom": "终端无法开机",
  "group_id": 1,
  "skill_group_id": 1,
  "owner_id": null,
  "is_duplicate": false,
  "duplicate_reason": null
}
```

**响应（201）：** 返回完整工单对象。

**重复检测：** 创建前自动检测，如存在重复工单，响应中额外返回：

```json
{
  "data": { ... },
  "warnings": {
    "duplicate_detected": true,
    "duplicate_tickets": [
      {
        "id": 5,
        "number": "TKT-00005",
        "title": "设备故障-无法开机",
        "state": "open",
        "created_at": "2026-06-15T10:00:00+08:00"
      }
    ]
  }
}
```

### PATCH /tickets/{id}

更新工单字段（状态、优先级、负责人等）。

**权限：** 有权访问该工单的用户

**请求（部分更新）：**

```json
{
  "state": "open",
  "priority": "p1_urgent",
  "owner_id": 2,
  "skill_group_id": 1
}
```

**业务规则：**
- 状态变更受状态机约束（见 PRD 7.2），非法流转返回 400
- 变更到 `on_hold` / `returned` 时需在 `reason` 字段填写原因
- 状态变更自动写入 ticket_state_logs
- 受理工单（pending → open）自动计算 SLA deadline
- 标记已处理（→ resolved）自动记录 solved_at

### POST /tickets/batch-update

批量更新工单。

**权限：** agent / admin

**请求：**

```json
{
  "ticket_ids": [1, 2, 3],
  "updates": {
    "state": "open",
    "priority": "p2_high",
    "owner_id": 2,
    "skill_group_id": 1
  }
}
```

**限制：** 单次最多 100 条；仅允许批量修改 state / priority / owner_id / skill_group_id。

### POST /tickets/{id}/cancel

撤销工单。

**权限：** 创建者 / 组长 / admin

**请求：**

```json
{
  "reason": "客户取消请求"
}
```

**业务规则：** 仅 pending / open / on_hold 状态可撤销。

### GET /tickets/{id}/state-logs

获取工单状态流转记录。

**权限：** 有权访问该工单的用户

**响应：**

```json
{
  "data": [
    {
      "id": 1,
      "from_state": null,
      "to_state": "pending",
      "operator_id": 1,
      "operator_name": "系统管理员",
      "reason": null,
      "duration_minutes": null,
      "created_at": "2026-06-16T15:30:00+08:00"
    },
    {
      "id": 2,
      "from_state": "pending",
      "to_state": "open",
      "operator_id": 2,
      "operator_name": "张三",
      "reason": null,
      "duration_minutes": 5,
      "created_at": "2026-06-16T15:35:00+08:00"
    }
  ]
}
```

---

## 6. 沟通记录（Article）

### GET /tickets/{ticket_id}/articles

获取工单的沟通记录列表。

**权限：** 有权访问该工单的用户；handler 不可见 internal_note 类型

**查询参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| type | string | 按类型筛选：reply / internal_note / addition / reminder |

### POST /tickets/{ticket_id}/articles

添加沟通记录。

**权限：** 有权访问该工单的用户

**请求：**

回复：

```json
{
  "type": "reply",
  "body": "已联系客户，确认故障原因，安排寄修"
}
```

内 note：

```json
{
  "type": "internal_note",
  "body": "客户情绪激动，需注意措辞"
}
```

追加：

```json
{
  "type": "addition",
  "body": "客户补充：设备购买时间为2025年3月",
  "append_reason": "客户补充设备信息"
}
```

催办：

```json
{
  "type": "reminder",
  "body": "请尽快处理，客户多次催促"
}
```

**业务规则：**
- reminder 类型自动触发钉钉通知给当前处理人
- addition 类型 append_reason 必填
- internal_note 类型仅 agent / admin 可见

---

## 7. 工单分类

### GET /categories

获取工单分类树。

**权限：** 已认证用户

**响应：**

```json
{
  "data": [
    {
      "id": 1,
      "name": "咨询",
      "level": 1,
      "children": [
        { "id": 101, "name": "产品咨询", "level": 2, "children": [] },
        { "id": 102, "name": "资费咨询", "level": 2, "children": [] }
      ]
    }
  ]
}
```

### POST /categories

创建分类。

**权限：** admin

### PATCH /categories/{id}

更新分类。

**权限：** admin

### DELETE /categories/{id}

删除分类（有关联工单时拒绝）。

**权限：** admin

---

## 8. 区域

### GET /regions

获取区域树。

**权限：** 已认证用户

**查询参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| parent_id | int | 获取某节点下的子区域（不传则返回全部） |
| level | int | 按层级筛选：1=省, 2=市, 3=区县, 4=站点 |

### POST /regions

创建区域。

**权限：** admin

### DELETE /regions/{id}

删除区域（有子区域或关联工单时拒绝）。

**权限：** admin

---

## 9. SLA 策略

### GET /sla-policies

获取 SLA 策略列表。

**权限：** admin

### POST /sla-policies

创建/更新 SLA 策略（skill_group_id + priority 唯一）。

**权限：** admin

**请求：**

```json
{
  "skill_group_id": 1,
  "priority": "p1_urgent",
  "first_response_minutes": 10,
  "solution_minutes": 90
}
```

### DELETE /sla-policies/{id}

删除 SLA 策略。

**权限：** admin

---

## 10. 统计与报表

### GET /stats/dashboard

获取仪表盘统计数据。

**权限：** agent / admin

**查询参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| group_id | int | 按客服组筛选（admin 可选，agent 默认本组） |

**响应：**

```json
{
  "data": {
    "pending_count": 12,
    "open_count": 34,
    "overdue_count": 3,
    "today_created": 8,
    "today_resolved": 5,
    "sla_breach_rate": 0.05,
    "first_contact_resolution_rate": 0.82,
    "avg_resolution_minutes": 245,
    "by_priority": {
      "p1_urgent": 2,
      "p2_high": 8,
      "p3_normal": 30,
      "p4_enterprise": 6
    },
    "by_category": {
      "咨询": 15,
      "报修": 20,
      "投诉": 5,
      "业务办理": 4,
      "合作洽谈": 2
    }
  }
}
```

### GET /stats/report

获取报表数据。

**权限：** agent(组长) / admin

**查询参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| period | string | 报表周期：daily / weekly / monthly / quarterly |
| date | date | 基准日期（默认今天） |
| group_id | int | 按客服组筛选 |
| skill_group_id | int | 按技能组筛选 |

**响应：**

```json
{
  "data": {
    "period": "daily",
    "date_range": { "from": "2026-06-16", "to": "2026-06-16" },
    "metrics": {
      "new_count": 8,
      "in_progress_count": 34,
      "closed_count": 5,
      "avg_resolution_minutes": 245,
      "sla_breach_rate": 0.05,
      "first_contact_resolution_rate": 0.82,
      "by_category": { ... },
      "by_skill_group": { ... }
    }
  }
}
```

---

## 11. 导出

### GET /tickets/export

导出工单数据（CSV）。

**权限：** agent / admin

**查询参数：** 同 GET /tickets 的筛选参数，另加：

| 参数 | 类型 | 说明 |
|------|------|------|
| columns | string[] | 导出列组：base / customer / category / workflow（逗号分隔，默认全部） |

**响应：** Content-Type: text/csv; charset=utf-8-sig（含 BOM，Excel 友好）

导出字段按 PRD 附件 1 规范：

| 列组 | 字段 |
|------|------|
| base | 工单编号、创建时间、结案时间、关闭时长、当前状态、来源 |
| customer | 用户姓名、联系手机号、设备编号/SN、所属区域、用户类型 |
| category | 一级分类、二级分类、故障现象描述、是否重复工单、优先级 |
| workflow | 首次受理坐席、归属技能组、流转记录、首次响应时间、SLA是否达标、处理备注、是否解决 |

---

## 12. 系统接口

### GET /healthz

健康检查。

### GET /readyz

就绪检查（含数据库连接）。

---

## 权限矩阵汇总

| 端点 | admin | agent | handler |
|------|-------|-------|---------|
| POST /auth/login | ✅ | ✅ | ✅ |
| GET /users | ✅ 全部 | ❌ | ❌ |
| POST/PATCH/DELETE /users | ✅ | ❌ | ❌ |
| GET /groups, /skill-groups | ✅ | ✅ | ✅ |
| POST/PATCH/DELETE /groups | ✅ | ❌ | ❌ |
| GET /tickets | ✅ 全部 | 本组+自己的 | 派给自己的 |
| POST /tickets | ✅ | ✅ | ❌ |
| PATCH /tickets/{id} | ✅ | 受理的 | 派给自己的 |
| POST /tickets/batch-update | ✅ | ✅ | ❌ |
| POST /tickets/{id}/cancel | ✅ | 创建者/组长 | ❌ |
| GET /tickets/{id}/state-logs | ✅ | 有权访问 | 有权访问 |
| POST /tickets/{id}/articles | ✅ | ✅ | ✅ |
| GET /categories, /regions | ✅ | ✅ | ✅ |
| CRUD /categories, /regions | ✅ | ❌ | ❌ |
| CRUD /sla-policies | ✅ | ❌ | ❌ |
| GET /stats/dashboard | ✅ | ✅ | ❌ |
| GET /stats/report | ✅ | 组长 | ❌ |
| GET /tickets/export | ✅ | ✅ | ❌ |
