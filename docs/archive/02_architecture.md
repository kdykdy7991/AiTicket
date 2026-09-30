# 02 系统架构（Architecture）

## 1. 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                      Client Layer                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  Vue 3 SPA   │  │  Email Client│  │  外部调用方   │  │
│  │  (Browser)   │  │  (IMAP/SMTP) │  │  (REST API)  │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │
└─────────┼─────────────────┼─────────────────┼───────────┘
          │ HTTPS           │ IMAP/SMTP       │ HTTPS
          ▼                 ▼                 ▼
┌─────────────────────────────────────────────────────────┐
│                    Application Layer                    │
│                                                         │
│  ┌─────────────────────────────────┐  ┌──────────────┐  │
│  │         FastAPI (Web)           │  │  ARQ Worker   │  │
│  │  ┌─────────────────────────┐   │  │  ┌──────────┐ │  │
│  │  │   API Router Layer      │   │  │  │ 邮件拉取  │ │  │
│  │  │   (api/v1/)             │   │  │  │ 邮件发送  │ │  │
│  │  ├─────────────────────────┤   │  │  │ SLA 检查  │ │  │
│  │  │   Service Layer         │   │  │  │ Trigger   │ │  │
│  │  │   (services/)           │   │  │  │ 执行      │ │  │
│  │  ├─────────────────────────┤   │  │  └──────────┘ │  │
│  │  │   Model Layer           │   │  │               │  │
│  │  │   (models/)             │   │  │               │  │
│  │  └─────────────────────────┘   │  └───────┬───────┘  │
│  └────────────┬───────────────────┘          │          │
└───────────────┼──────────────────────────────┼──────────┘
                │                              │
                ▼                              ▼
┌─────────────────────────────────────────────────────────┐
│                   Infrastructure Layer                  │
│  ┌──────────────────────┐  ┌─────────────────────────┐  │
│  │   PostgreSQL 15      │  │      Redis 7            │  │
│  │   - 数据持久化        │  │   - ARQ 任务队列         │  │
│  │   - 全文检索          │  │   - 缓存（会话/配置）     │  │
│  │   - 审计日志          │  │   - 限流计数器           │  │
│  └──────────────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## 2. 后端分层设计

采用经典三层架构，职责严格分离：

### 2.1 API Router 层（`api/`）

- 定义 HTTP 端点（路径、方法、状态码）
- 请求参数校验（Pydantic schema）
- JWT 鉴权 + 角色权限检查（通过 `Depends`）
- 调用 Service 层，不包含业务逻辑
- 统一异常处理（通过 `exception_handler` 捕获 Service 层抛出的业务异常）

### 2.2 Service 层（`services/`）

核心业务逻辑所在，所有非 trivial 操作都在此层完成：

| Service | 职责 |
|---|---|
| `auth_service` | 登录验证、JWT 签发/刷新、密码变更 |
| `user_service` | 用户 CRUD、角色分配、Group 关联 |
| `ticket_service` | 工单 CRUD、状态机流转、分配、合并 |
| `article_service` | Article 追加、sender_type 判断 |
| `sla_service` | SLA 计算（escalation_at）、超时检查 |
| `trigger_service` | 条件匹配、动作执行、异步 dispatch |
| `overview_service` | 动态查询构建、结果分页 |
| `email_service` | IMAP 拉取、SMTP 发送、邮件解析 |
| `notification_service` | 通知事件生成、邮件模板渲染 |
| `search_service` | PostgreSQL 全文检索封装 |

### 2.3 Model 层（`models/`）

- SQLAlchemy 2.0 声明式映射（`DeclarativeBase`）
- 只定义表结构、关系映射、基本属性
- 不包含业务逻辑（不在 Model 里写 `save()` 或 `validate()`）

### 2.4 Schema 层（`schemas/`）

- Pydantic v2 模型，分离请求（`Create`/`Update`）和响应（`Read`/`List`）
- 复用基类减少重复（`TimestampMixin`、`PaginatedResponse`）

## 3. 前端架构

```
Vue 3 SPA
├── Vue Router          路由管理 + 导航守卫（鉴权）
├── Pinia               状态管理（auth / tickets / overviews / ui）
├── Axios               HTTP 请求 + 拦截器（token 注入 + 自动刷新）
├── Element Plus        UI 组件库
└── Vite                构建工具 + HMR 开发服务器
```

采用 **Layout → Page → Section → Widget** 四层组件结构：
- **Layout**：整体框架（侧边栏 + 顶栏 + 内容区）
- **Page**：路由对应的页面组件
- **Section**：页面内的独立区块（如工单详情的 Article 时间线、信息侧栏）
- **Widget**：可复用的小组件（状态标签、优先级图标、用户头像）

## 4. 项目目录结构

```
Skdy_Ticket_System/
├── docs/                           # 设计文档
│   ├── 00_overview.md
│   ├── 01_requirements.md
│   ├── 02_architecture.md
│   ├── 03_data_model.md
│   ├── 04_api_design.md
│   ├── 05_frontend_design.md
│   └── 06_implementation_plan.md
│
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                 # FastAPI app 入口
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── config.py           # Settings（pydantic-settings）
│   │   │   ├── database.py         # async engine + session factory
│   │   │   ├── security.py         # JWT 签发/验证、密码哈希
│   │   │   ├── deps.py             # FastAPI 依赖注入（get_db, get_current_user）
│   │   │   └── exceptions.py       # 业务异常类定义
│   │   │
│   │   ├── models/
│   │   │   ├── __init__.py         # Base + 全部 model 导入
│   │   │   ├── base.py             # DeclarativeBase + 通用 Mixin
│   │   │   ├── user.py             # User, Role, UserGroup
│   │   │   ├── organization.py     # Organization
│   │   │   ├── group.py            # Group
│   │   │   ├── ticket.py           # Ticket, TicketState, TicketPriority
│   │   │   ├── article.py          # Article
│   │   │   ├── link.py             # TicketLink
│   │   │   ├── sla.py              # SLAPolicy, Calendar
│   │   │   ├── trigger.py          # Trigger
│   │   │   ├── overview.py         # Overview
│   │   │   ├── channel.py          # EmailChannel
│   │   │   └── audit_log.py        # AuditLog
│   │   │
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── common.py           # PaginatedResponse, ErrorResponse
│   │   │   ├── auth.py
│   │   │   ├── user.py
│   │   │   ├── ticket.py
│   │   │   ├── article.py
│   │   │   ├── sla.py
│   │   │   ├── trigger.py
│   │   │   ├── overview.py
│   │   │   └── channel.py
│   │   │
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── auth_service.py
│   │   │   ├── user_service.py
│   │   │   ├── ticket_service.py
│   │   │   ├── article_service.py
│   │   │   ├── sla_service.py
│   │   │   ├── trigger_service.py
│   │   │   ├── overview_service.py
│   │   │   ├── email_service.py
│   │   │   ├── notification_service.py
│   │   │   └── search_service.py
│   │   │
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   └── v1/
│   │   │       ├── __init__.py
│   │   │       ├── router.py       # 汇总所有子路由
│   │   │       ├── auth.py
│   │   │       ├── users.py
│   │   │       ├── groups.py
│   │   │       ├── organizations.py
│   │   │       ├── tickets.py
│   │   │       ├── articles.py
│   │   │       ├── links.py
│   │   │       ├── sla.py
│   │   │       ├── triggers.py
│   │   │       ├── overviews.py
│   │   │       ├── channels.py
│   │   │       ├── search.py
│   │   │       └── health.py
│   │   │
│   │   └── tasks/
│   │       ├── __init__.py
│   │       ├── worker.py           # ARQ worker 配置
│   │       ├── email_fetch.py      # 定时拉取 IMAP 邮件
│   │       ├── email_send.py       # 异步发送邮件
│   │       ├── sla_check.py        # 定时 SLA 超时检查
│   │       └── trigger_exec.py     # 异步执行 Trigger 动作
│   │
│   ├── alembic/
│   │   ├── alembic.ini
│   │   ├── env.py
│   │   └── versions/
│   │
│   ├── tests/
│   │   ├── conftest.py             # 测试 fixtures（test db, client）
│   │   ├── test_auth.py
│   │   ├── test_tickets.py
│   │   ├── test_articles.py
│   │   ├── test_sla.py
│   │   ├── test_triggers.py
│   │   └── test_email.py
│   │
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── .env.example
│
├── frontend/
│   ├── src/
│   │   ├── main.ts
│   │   ├── App.vue
│   │   ├── api/
│   │   │   ├── index.ts            # axios 实例 + 拦截器
│   │   │   ├── auth.ts
│   │   │   ├── tickets.ts
│   │   │   ├── users.ts
│   │   │   └── admin.ts
│   │   ├── router/
│   │   │   └── index.ts
│   │   ├── stores/
│   │   │   ├── auth.ts
│   │   │   ├── ticket.ts
│   │   │   ├── overview.ts
│   │   │   └── ui.ts
│   │   ├── layouts/
│   │   │   ├── DefaultLayout.vue   # Agent/Admin 主布局
│   │   │   └── AuthLayout.vue      # 登录页布局
│   │   ├── views/
│   │   │   ├── LoginView.vue
│   │   │   ├── DashboardView.vue
│   │   │   ├── TicketListView.vue
│   │   │   ├── TicketDetailView.vue
│   │   │   ├── TicketCreateView.vue
│   │   │   └── admin/
│   │   │       ├── UserManageView.vue
│   │   │       ├── GroupManageView.vue
│   │   │       ├── TriggerManageView.vue
│   │   │       ├── SLAManageView.vue
│   │   │       └── ChannelManageView.vue
│   │   ├── components/
│   │   │   ├── ticket/
│   │   │   │   ├── ArticleTimeline.vue
│   │   │   │   ├── TicketInfoSidebar.vue
│   │   │   │   ├── TicketFilters.vue
│   │   │   │   └── ReplyEditor.vue
│   │   │   └── common/
│   │   │       ├── StateTag.vue
│   │   │       ├── PriorityIcon.vue
│   │   │       ├── UserAvatar.vue
│   │   │       └── SLAIndicator.vue
│   │   ├── composables/
│   │   │   ├── useAuth.ts
│   │   │   └── usePagination.ts
│   │   └── types/
│   │       └── index.ts            # TypeScript 类型定义
│   │
│   ├── index.html
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── package.json
│   └── Dockerfile
│
├── docker-compose.yml
├── .gitignore
└── README.md
```

## 5. 关键中间件与横切关注点

### 5.1 JWT 鉴权

```
请求 → CORSMiddleware → JWT 验证（Depends） → 角色权限检查 → Router Handler
```

- `access_token`：有效期 30 分钟，放在 `Authorization: Bearer <token>` 头
- `refresh_token`：有效期 7 天，仅用于 `/api/v1/auth/refresh`
- 权限检查通过 FastAPI `Depends` 链实现（`get_current_user` → `require_role(["admin"])`）

### 5.2 异常处理

定义业务异常层级：

```
AppException (base)
├── AuthenticationError     → 401
├── AuthorizationError      → 403
├── NotFoundError           → 404
├── ConflictError           → 409
├── ValidationError         → 422
└── BusinessRuleError       → 400
```

在 `main.py` 注册全局 `exception_handler`，统一返回：

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Ticket #1234 not found"
  }
}
```

### 5.3 请求日志

使用 FastAPI middleware 记录每个请求的结构化日志：

```json
{
  "timestamp": "2026-05-29T10:00:00Z",
  "method": "POST",
  "path": "/api/v1/tickets",
  "status": 201,
  "duration_ms": 45,
  "user_id": 12,
  "request_id": "uuid"
}
```

### 5.4 CORS

开发环境允许 `http://localhost:5173`（Vite dev server），生产环境通过环境变量配置允许的 Origin。

## 6. 事件与异步任务模型

### 6.1 同步事件流

Ticket/Article 的 create/update 在 Service 层完成后，同步执行：
1. 写入 `audit_logs` 表
2. 将需要异步处理的事件 enqueue 到 ARQ

### 6.2 ARQ 异步任务

| 任务 | 触发方式 | 说明 |
|---|---|---|
| `trigger_exec` | 事件驱动 | Ticket/Article 变更后，匹配 Trigger 条件并执行动作 |
| `email_send` | 事件驱动 | 发送通知邮件（分配、新回复、状态变更、SLA 超时） |
| `email_fetch` | 定时（cron 60s） | 拉取 IMAP 邮件，解析后创建 Ticket 或追加 Article |
| `sla_check` | 定时（cron 60s） | 扫描未关闭工单，检查 SLA 是否即将超时或已超时 |

### 6.3 事件传递简图

```
Service 层操作完成
    │
    ├──→ 写入 audit_log（同步）
    │
    └──→ ARQ enqueue
            │
            ├── trigger_exec  ──→  匹配条件 → 执行动作（可能再 enqueue email_send）
            ├── email_send    ──→  渲染模板 → SMTP 发送
            ├── email_fetch   ──→  IMAP 拉取 → 解析 → 创建/更新 Ticket
            └── sla_check     ──→  扫描工单 → 标记超时 → enqueue email_send
```

## 7. 部署架构（Docker Compose）

```yaml
services:
  app:           # FastAPI Web 服务
    build: ./backend
    ports: ["8000:8000"]
    depends_on: [db, redis]

  worker:        # ARQ 异步任务 Worker
    build: ./backend
    command: arq app.tasks.worker.WorkerSettings
    depends_on: [db, redis]

  frontend:      # Vue 3 SPA（生产环境用 nginx 静态托管）
    build: ./frontend
    ports: ["80:80"]

  db:            # PostgreSQL
    image: postgres:15
    volumes: [pgdata:/var/lib/postgresql/data]

  redis:         # Redis
    image: redis:7-alpine

volumes:
  pgdata:
```

生产环境建议在 `frontend` 容器中配置 nginx 反向代理，将 `/api` 请求转发到 `app:8000`。

## 8. 安全设计

| 层面 | 措施 |
|---|---|
| 传输 | 生产环境强制 HTTPS（nginx / LB 层终止 TLS） |
| 认证 | JWT HS256，access_token 短有效期 + refresh_token 长有效期 |
| 密码 | bcrypt hash，cost = 12 |
| 权限 | 行级权限：Customer 只能访问自己的工单，Agent 只能访问所在 Group 的工单 |
| 注入 | SQLAlchemy ORM 参数化查询，杜绝 SQL 注入 |
| XSS | 邮件正文存储原始 HTML，前端渲染前转义；API 返回时标记 content_type |
| 敏感配置 | 数据库密码、JWT 密钥、邮箱密码通过环境变量注入，不入库不入代码 |
| 限流 | Redis + 滑动窗口，登录接口 5 次/分钟，API 100 次/分钟 |
