# 06 实施计划（Implementation Plan）

## 1. 分阶段里程碑

```
Week 1          Week 2          Week 3          Week 4          Week 5          Week 6
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│ P1 基础   │   │ P2 工单   │   │ P3 高级   │   │ P4 渠道   │   │ P5 前端   │   │ P6 收尾   │
│ 骨架      │──▶│ 核心      │──▶│ 特性      │──▶│ & 通知    │──▶│          │──▶│          │
└──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘
```

---

## 2. P1 基础骨架（Week 1）

**目标：** 项目初始化，跑通从请求到数据库的完整链路。

### 交付物

| # | 任务 | 文件/模块 |
|---|---|---|
| 1.1 | 初始化后端项目结构 | `backend/pyproject.toml`、目录骨架 |
| 1.2 | Docker Compose 环境 | `docker-compose.yml`（app + db + redis） |
| 1.3 | FastAPI 应用入口 + 配置 | `app/main.py`、`app/core/config.py` |
| 1.4 | 数据库连接（async） | `app/core/database.py` |
| 1.5 | 基础 Model（User, Role, Group, Organization） | `app/models/` |
| 1.6 | Alembic 初始化 + 首次 migration | `alembic/` |
| 1.7 | JWT 认证（登录/刷新/密码哈希） | `app/core/security.py`、`app/services/auth_service.py` |
| 1.8 | Auth API（login/refresh/password） | `app/api/v1/auth.py` |
| 1.9 | User CRUD API | `app/api/v1/users.py` |
| 1.10 | 中间件（CORS、请求日志、异常处理） | `app/main.py` |
| 1.11 | 健康检查端点 | `app/api/v1/health.py` |
| 1.12 | 种子数据脚本 | `backend/scripts/seed.py` |
| 1.13 | 测试基础设施 | `tests/conftest.py` |

### 验收标准

- [x] `docker-compose up` 后服务正常启动，`/healthz` 返回 200
- [x] 运行 seed 脚本后，可用默认 admin 账号登录获取 JWT
- [x] User CRUD API 全部可用，权限检查生效
- [x] `pytest` 通过基础测试

---

## 3. P2 工单核心（Week 2）

**目标：** 实现完整的工单生命周期（创建 → 分配 → 回复 → 状态流转）。

### 交付物

| # | 任务 | 文件/模块 |
|---|---|---|
| 2.1 | Ticket Model（含 State、Priority） | `app/models/ticket.py` |
| 2.2 | Article Model | `app/models/article.py` |
| 2.3 | Migration（tickets + articles 表） | `alembic/versions/` |
| 2.4 | 工单编号生成器（TKT-00001 序列） | `app/services/ticket_service.py` |
| 2.5 | Ticket CRUD Service + API | `app/services/`、`app/api/v1/tickets.py` |
| 2.6 | 状态机流转校验 | `app/services/ticket_service.py` |
| 2.7 | Article CRUD Service + API | `app/services/`、`app/api/v1/articles.py` |
| 2.8 | Group / Organization CRUD API | `app/api/v1/groups.py`、`organizations.py` |
| 2.9 | 行级权限（Customer 看自己的、Agent 看组内的） | `app/core/deps.py` |
| 2.10 | 审计日志记录 | `app/models/audit_log.py`、`app/services/` |
| 2.11 | 工单核心测试 | `tests/test_tickets.py`、`test_articles.py` |

### 验收标准

- [x] Customer 创建工单 → Agent 列表中可见 → Agent 回复 → Customer 查看回复
- [x] 状态机流转：new → open → pending → resolved → closed，非法转换返回 400
- [x] Customer 无法访问其他人的工单，Agent 无法访问非所在 Group 的工单
- [x] 所有 create/update 操作产生 audit_log 记录

---

## 4. P3 高级特性（Week 3）

**目标：** SLA、Trigger、Overview、Link、搜索。

### 交付物

| # | 任务 | 文件/模块 |
|---|---|---|
| 3.1 | SLA Policy + Calendar Model | `app/models/sla.py` |
| 3.2 | SLA 计算引擎（工作日历感知） | `app/services/sla_service.py` |
| 3.3 | SLA 超时检查定时任务 | `app/tasks/sla_check.py` |
| 3.4 | SLA API（CRUD + Calendar CRUD） | `app/api/v1/sla.py` |
| 3.5 | Trigger Model | `app/models/trigger.py` |
| 3.6 | Trigger 条件匹配引擎 | `app/services/trigger_service.py` |
| 3.7 | Trigger 动作执行器 | `app/services/trigger_service.py` |
| 3.8 | Trigger 异步执行任务 | `app/tasks/trigger_exec.py` |
| 3.9 | Trigger API（CRUD） | `app/api/v1/triggers.py` |
| 3.10 | Overview Model + 动态查询构建 | `app/services/overview_service.py` |
| 3.11 | Overview API（CRUD + 执行查询） | `app/api/v1/overviews.py` |
| 3.12 | Ticket Link Model + API | `app/models/link.py`、`app/api/v1/links.py` |
| 3.13 | Ticket 合并（merge）逻辑 | `app/services/ticket_service.py` |
| 3.14 | 全文检索（PostgreSQL tsvector） | `app/services/search_service.py` |
| 3.15 | Search API | `app/api/v1/search.py` |
| 3.16 | Stats API（dashboard 统计） | `app/api/v1/stats.py` |
| 3.17 | 高级特性测试 | `tests/test_sla.py`、`test_triggers.py` |

### 验收标准

- [x] 创建 SLA 策略后，新工单的 escalation_at 被正确计算（跳过非工作时间）
- [x] SLA 定时任务检测到超时工单并标记
- [x] 配置 Trigger "新工单自动分配默认组" → 创建工单后自动分配
- [x] Overview "我的待处理" 返回当前用户负责的未关闭工单
- [x] 搜索 "登录" 返回标题或正文包含该关键词的工单

---

## 5. P4 渠道与通知（Week 4）

**目标：** 邮件渠道接入 + 通知系统。

### 交付物

| # | 任务 | 文件/模块 |
|---|---|---|
| 4.1 | ARQ Worker 配置 | `app/tasks/worker.py` |
| 4.2 | Email Channel Model + API | `app/models/channel.py`、`app/api/v1/channels.py` |
| 4.3 | IMAP 邮件拉取（定时任务） | `app/tasks/email_fetch.py` |
| 4.4 | 邮件解析（subject/body/sender） | `app/services/email_service.py` |
| 4.5 | `[Ticket#X]` 标识识别 + Article 追加 | `app/services/email_service.py` |
| 4.6 | SMTP 邮件发送（异步） | `app/tasks/email_send.py` |
| 4.7 | 邮件模板（通知、SLA 超时提醒） | `app/services/notification_service.py` |
| 4.8 | 通知事件生成（分配、新 Article、状态变更） | `app/services/notification_service.py` |
| 4.9 | 邮件渠道连接测试端点 | `app/api/v1/channels.py` |
| 4.10 | 渠道与通知测试 | `tests/test_email.py` |

### 验收标准

- [x] 配置 IMAP 渠道后，发送邮件到该邮箱 → 60s 内自动创建工单
- [x] 邮件 subject 包含 `[Ticket#42]` → Article 追加到工单 42
- [x] Agent 被分配工单后收到邮件通知
- [x] 工单有新 Article 时，owner 收到邮件通知
- [x] 发出的通知邮件 subject 包含 `[Ticket#X]` 用于回信识别

---

## 6. P5 前端（Week 4-5，与 P4 并行开始）

**目标：** 实现可用的 Web SPA。

### 交付物

| # | 任务 | 文件/模块 |
|---|---|---|
| 5.1 | 前端项目初始化（Vue 3 + TS + Vite） | `frontend/` 基础结构 |
| 5.2 | Axios 实例 + 拦截器 + token 刷新 | `src/api/index.ts` |
| 5.3 | Pinia stores（auth, ticket, overview, ui） | `src/stores/` |
| 5.4 | Vue Router + 路由守卫 | `src/router/` |
| 5.5 | Layout 组件（Default + Customer + Auth） | `src/layouts/` |
| 5.6 | 登录页 | `src/views/LoginView.vue` |
| 5.7 | Dashboard 页（统计卡片 + Overview 面板） | `src/views/DashboardView.vue` |
| 5.8 | 工单列表页（筛选、排序、分页、SLA 标记） | `src/views/TicketListView.vue` |
| 5.9 | 工单详情页（Article 时间线 + 侧栏 + 回复） | `src/views/TicketDetailView.vue` |
| 5.10 | 新建工单页 | `src/views/TicketCreateView.vue` |
| 5.11 | 搜索结果页 | `src/views/SearchView.vue` |
| 5.12 | 通用组件（StateTag, PriorityIcon, SLAIndicator...） | `src/components/common/` |
| 5.13 | 管理后台 — 用户管理 | `src/views/admin/UserManageView.vue` |
| 5.14 | 管理后台 — 组管理 | `src/views/admin/GroupManageView.vue` |
| 5.15 | 管理后台 — Trigger 配置 | `src/views/admin/TriggerManageView.vue` |
| 5.16 | 管理后台 — SLA 配置 | `src/views/admin/SLAManageView.vue` |
| 5.17 | 管理后台 — 邮件渠道配置 | `src/views/admin/ChannelManageView.vue` |
| 5.18 | Customer 端页面（我的工单、提交、详情） | `src/views/my/` |
| 5.19 | Frontend Dockerfile + nginx 配置 | `frontend/Dockerfile`、`nginx.conf` |

### 验收标准

- [x] 完整走通场景 A：Customer 提交工单 → Agent 在列表中看到 → 查看详情 → 回复 → 关闭
- [x] Dashboard Overview 面板正确显示"我的待处理"、"逾期工单"等
- [x] SLA 即将超时的工单在列表中有颜色标记
- [x] Admin 可在管理后台配置用户、组、Trigger、SLA
- [x] 前端 build 成功，nginx 托管静态文件 + 反代 API

---

## 7. P6 收尾（Week 6）

**目标：** 测试覆盖率达标、部署验证、文档完善。

### 交付物

| # | 任务 |
|---|---|
| 6.1 | 补充单元测试，核心 service 覆盖率 ≥ 70% |
| 6.2 | 集成测试（端到端场景 A + 场景 B） |
| 6.3 | Seed 数据完善（演示用样本数据） |
| 6.4 | docker-compose 完整部署测试 |
| 6.5 | README.md（快速开始、环境变量说明、API 文档链接） |
| 6.6 | 冒烟测试脚本 |
| 6.7 | 已知问题与 V2 规划记录 |

### 验收标准

- [x] `docker-compose up` 后 10 分钟内完成端到端冒烟测试
- [x] `pytest --cov` 核心 service 覆盖率 ≥ 70%
- [x] README 包含从零启动的完整步骤
- [x] 场景 A（正常工单流程）和场景 B（SLA 超时）自动化测试通过

---

## 8. 技术风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| SLA 工作日历计算复杂度高 | 计算不准确，客户投诉 | 参考 Zammad 逻辑简化实现；编写大量边界测试（跨天、节假日、时区） |
| Trigger 条件匹配性能 | 工单量大时 Trigger 执行慢 | MVP 阶段 Trigger 数量有限（< 50），走简单遍历匹配；异步执行不阻塞请求 |
| IMAP 邮件解析兼容性 | 不同邮件客户端格式差异大 | 使用 Python `email` 标准库 + `beautifulsoup4` 处理 HTML；记录解析失败日志，不丢邮件 |
| JWT token 泄露 | 未授权访问 | access_token 短有效期（30min）；refresh_token 绑定 IP（可选）；关键操作二次验证（V2） |
| 前后端并行开发协调 | API 接口变更导致前端返工 | P1 结束后固定核心 API Schema（Pydantic → OpenAPI）；前端用 mock 数据先行开发 |
| PostgreSQL 全文检索中文分词 | 搜索效果差 | 使用 `simple` 或 `zhparser` 分词配置；MVP 可接受基础效果，V2 考虑 Elasticsearch |

---

## 9. 依赖关系

```
P1 基础骨架
    │
    ▼
P2 工单核心
    │
    ├──────────────┐
    ▼              ▼
P3 高级特性    P5 前端（可与 P3 并行，先用 mock）
    │              │
    ▼              │
P4 渠道与通知      │
    │              │
    ├──────┬───────┤
    ▼      ▼       ▼
  P7 客服组需求补充（见 §10）
    │              │
    └──────┬───────┘
           ▼
       P6 收尾
```

P5（前端）可以在 P2 完成后就开始，使用 OpenAPI 文档对接已有 API，高级特性 API 用 mock 数据。
P7（客服组需求补充）依赖 P2 + P3 的基础，独立于 P4 邮件渠道，可与 P4 并行；其前端子任务 P1（7.9-7.16）需要 P5 的基础组件就绪。

---

## 10. P7 客服组需求补充（Week 7-8，待评审）

**目标：** 补齐客户《客服组端到端工单模块需求补充.docx》提出的所有字段与功能（详见 `07_requirements_supplement.md`）。

### 交付物

| # | 任务 | 文件/模块 | 优先级 |
|---|---|---|---|
| 7.1 | `tickets` 表增量字段迁移（customer_type / phone / device_sn / contact / region / category / symptom / duplicate / first_owner / skill_group / sla_breached / resolved / resolution） | `alembic/versions/` + `app/models/ticket.py` | P0 |
| 7.2 | 新表 `ticket_categories`（树状分类）+ `regions`（行政区树）+ `ticket_state_logs`（流转时长） | `app/models/` + Alembic migration + seed | P0 |
| 7.3 | `ticket_states` / `ticket_priorities` / `channel` 枚举扩展（待回访 / 已回访 / 政企特急 / phone / wechat / app） | `app/models/` + `backend/scripts/seed.py` | P0 |
| 7.4 | 状态机扩展：`open → awaiting_callback → callbacked` 合法转换 | `app/services/ticket_service.py` | P0 |
| 7.5 | `articles` 表加 `is_addition` / `append_reason` 字段 | Alembic + `app/models/article.py` | P0 |
| 7.6 | 重投工单检测服务（按手机号+SN+一级分类查 30 天） | `app/services/duplicate_service.py` + API `POST /api/v1/tickets/check-duplicate` | P0 |
| 7.7 | 创建工单时支持新字段入参 | `app/schemas/ticket.py` + `POST /api/v1/tickets` | P0 |
| 7.8 | 前端 `types/index.ts` 同步扩展（Ticket / Article / DashboardStats / Filter） | `frontend/src/types/index.ts` | P0 |
| 7.9 | 前端 `TicketCreateView.vue` 表单补全（用户信息/区域级联/重投/分类/故障描述）| `frontend/src/views/TicketCreateView.vue` | P1 |
| 7.10 | 新组件 `DuplicateTicketWarning.vue`（创建时弹窗疑似重复工单） | `frontend/src/components/ticket/` | P1 |
| 7.11 | 新组件 `StateLogTimeline.vue`（工单详情流转时间线） | `frontend/src/components/ticket/` | P1 |
| 7.12 | 新组件 `CustomerTypeChip.vue`（政企加急标识） | `frontend/src/components/common/` | P1 |
| 7.13 | `TicketTable.vue` 加 `type="selection"` + 批量操作工具栏（改状态/分配/组/优先级） | `frontend/src/components/ticket/TicketTable.vue` + `TicketListView.vue` | P1 |
| 7.14 | `TicketTable.vue` 加 `row-class-name`（即将超时 warning / 已超时 danger 底色） | `frontend/src/components/ticket/TicketTable.vue` | P1 |
| 7.15 | `ReplyEditor.vue` 支持追加模式（is_addition + append_reason） | `frontend/src/components/ticket/ReplyEditor.vue` | P1 |
| 7.16 | `TicketInfoSidebar.vue` 状态选项加 `awaiting_callback` / `callbacked` + 渠道 chip 颜色 | `frontend/src/components/ticket/TicketInfoSidebar.vue` | P1 |
| 7.17 | `DashboardView.vue` 加"处理中量 / 超时率 / 一次解决率 / 各组平均时长 / 故障分类"卡片 | `frontend/src/views/DashboardView.vue` | P2 |
| 7.18 | `GET /api/v1/tickets/export?format=csv\|xlsx&...filters` 后端实现 | `app/api/v1/tickets.py` + `app/services/export_service.py` | P2 |
| 7.19 | 前端"导出"按钮 + 4 大块 22 列字段拼装 | `frontend/src/views/TicketListView.vue` | P2 |
| 7.20 | `DashboardStats` 统计 SQL（各组平均时长 / 一次解决率 / 故障分类） | `app/services/stats_service.py` | P2 |
| 7.21 | 状态流转日志写入（手动 + Trigger 触发时） | `app/services/ticket_service.py` | P1 |
| 7.22 | P7 相关测试（重投检测 / 批量操作 / 导出 / 状态机扩展） | `tests/test_supplement.py` | P0 |

### 验收标准

- [ ] 创建工单时可录入手机号/终端 SN/区域/分类/重投原因
- [ ] 同一手机号 + SN + 一级分类在 30 天内有未关闭工单 → 创建时弹窗
- [ ] 政企客户工单展示"政企"chip，优先级可设为"政企特急"
- [ ] 列表行底色：剩余 > 20% 正常，0-20% warning，< 0% danger
- [ ] 工单可勾选批量改状态/分配/组/优先级
- [ ] 工单详情"流转时间线"显示每个状态停留时长
- [ ] Dashboard 显示超时率 / 一次解决率 / 各组平均时长 / 故障分类
- [ ] 列表页"导出"按钮按当前筛选条件生成 CSV/XLSX，含 4 大块 22 列

### 依赖关系

```
P0（基础）→ P2（工单核心）→ P3（高级）
                          → P5（前端，mock 先跑）
                          → P7（本阶段）┐
                                            ↓
                                       P6（收尾）
```

P7 中 P0 子任务（7.1-7.8、7.22）必须先于 P1（7.9-7.16、7.21），P1 先于 P2（7.17-7.20）。

---

## 11. V2 候选特性

以下特性明确排除在 MVP 之外，作为 V2 规划参考：

- WebSocket 实时推送（新工单通知、工单状态变更实时更新）
- 附件上传（Article 附件、截图）
- 知识库（KB）
- 客户自助门户（FAQ + 工单查询）
- 移动端适配（响应式 or 小程序）
- 国际化（i18n）
- 更多渠道（微信、钉钉、电话）
- 工单自定义字段
- 报表与数据导出
- LDAP / SSO 集成
