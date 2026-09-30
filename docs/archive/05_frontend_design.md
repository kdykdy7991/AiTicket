# 05 前端设计（Frontend Design）

## 1. 技术栈

| 技术 | 版本 | 用途 |
|---|---|---|
| Vue 3 | 3.4+ | 框架（Composition API） |
| TypeScript | 5.x | 类型安全 |
| Vue Router | 4.x | 路由管理 |
| Pinia | 2.x | 状态管理 |
| Element Plus | 2.x | UI 组件库 |
| Axios | 1.x | HTTP 请求 |
| Vite | 5.x | 构建工具 |
| TipTap | 2.x | 富文本编辑器（Article 回复） |

## 2. 页面路由表

### 2.1 公共路由（无需登录）

| 路径 | 页面组件 | 说明 |
|---|---|---|
| `/login` | `LoginView` | 登录页 |

### 2.2 Agent / Admin 路由

| 路径 | 页面组件 | 权限 | 说明 |
|---|---|---|---|
| `/` | → redirect `/dashboard` | agent+ | |
| `/dashboard` | `DashboardView` | agent+ | 仪表盘（Overview 面板 + 统计） |
| `/tickets` | `TicketListView` | agent+ | 工单列表（筛选、排序、分页） |
| `/tickets/new` | `TicketCreateView` | agent+ | 新建工单 |
| `/tickets/:id` | `TicketDetailView` | agent+ | 工单详情（Article 时间线） |
| `/search` | `SearchView` | agent+ | 全文搜索结果页 |

### 2.3 Admin 管理后台路由

| 路径 | 页面组件 | 权限 | 说明 |
|---|---|---|---|
| `/admin/users` | `UserManageView` | admin | 用户管理 |
| `/admin/groups` | `GroupManageView` | admin | 客服组管理 |
| `/admin/organizations` | `OrgManageView` | admin | 组织管理 |
| `/admin/triggers` | `TriggerManageView` | admin | 触发器配置 |
| `/admin/sla` | `SLAManageView` | admin | SLA 策略管理 |
| `/admin/calendars` | `CalendarManageView` | admin | 日历管理 |
| `/admin/overviews` | `OverviewManageView` | admin | 视图管理 |
| `/admin/channels` | `ChannelManageView` | admin | 邮件渠道配置 |

### 2.4 Customer 路由

| 路径 | 页面组件 | 权限 | 说明 |
|---|---|---|---|
| `/my/tickets` | `MyTicketListView` | customer | 我的工单列表 |
| `/my/tickets/new` | `MyTicketCreateView` | customer | 提交工单 |
| `/my/tickets/:id` | `MyTicketDetailView` | customer | 查看工单详情 + 回复 |

### 2.5 路由守卫

```
beforeEach:
  1. 无 token → 跳转 /login（白名单路由除外）
  2. token 过期 → 尝试 refresh；失败 → /login
  3. 检查角色权限：
     - /admin/* → 需要 admin 角色
     - /my/*    → customer 角色
     - 其他     → agent 或 admin
  4. 权限不足 → 跳转到对应角色的默认页
```

## 3. 页面布局

### 3.1 布局组件

**DefaultLayout**（Agent / Admin）

```
┌──────────────────────────────────────────────────┐
│  TopBar（logo, 搜索框, 用户菜单）                  │
├────────┬─────────────────────────────────────────┤
│        │                                         │
│  Side  │           Content Area                  │
│  Bar   │                                         │
│        │                                         │
│ - 仪表盘│                                         │
│ - 工单  │                                         │
│ - 管理  │                                         │
│   └ 用户│                                         │
│   └ 组  │                                         │
│   └ SLA │                                         │
│   └ ... │                                         │
│        │                                         │
└────────┴─────────────────────────────────────────┘
```

- 侧边栏宽度 220px，支持折叠
- 管理菜单仅 admin 可见
- 侧边栏底部显示当前用户信息 + 设置/登出

**CustomerLayout**（Customer）

```
┌──────────────────────────────────────────────────┐
│  TopBar（logo, 用户菜单）                          │
├──────────────────────────────────────────────────┤
│                                                  │
│                Content Area                      │
│                                                  │
└──────────────────────────────────────────────────┘
```

- 无侧边栏，简化布局
- 仅展示"我的工单"和"提交工单"

**AuthLayout**（登录页）

```
┌──────────────────────────────────────────────────┐
│                                                  │
│              居中 Login Card                      │
│              ┌─────────────┐                     │
│              │ Logo        │                     │
│              │ Email       │                     │
│              │ Password    │                     │
│              │ [Login]     │                     │
│              └─────────────┘                     │
│                                                  │
└──────────────────────────────────────────────────┘
```

### 3.2 关键页面设计

**DashboardView**

```
┌─────────────────────────────────────────────────────┐
│ 统计卡片行                                            │
│ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐       │
│ │新工单 │ │进行中│ │待处理│ │已逾期 │ │今日解决│      │
│ │  12   │ │  34  │ │  8   │ │  3   │ │  6   │       │
│ └──────┘ └──────┘ └──────┘ └──────┘ └──────┘       │
├─────────────────────────────────────────────────────┤
│ Overview 面板（Tab 切换）                             │
│ ┌─────────────────┬──────────────────────────────┐  │
│ │ [我的待处理]     │  TKT-042  登录页面无法访问      │  │
│ │ [组内未分配]     │  TKT-041  订单查询报错          │  │
│ │ [逾期工单]       │  TKT-039  密码重置失败          │  │
│ │                  │  ...                          │  │
│ └─────────────────┴──────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

**TicketDetailView**

```
┌─────────────────────────────────────┬──────────────┐
│ 工单标题区                           │ 信息侧栏      │
│ TKT-00042 登录页面无法访问            │              │
│ [状态: open]                        │ 优先级: high  │
├─────────────────────────────────────┤ 部门对接人: 李│
│ 详细描述                             │ 处理人: 张三  │
│ 从今天上午开始登录页面 502...        │ 客服组: 技术组│
├─────────────────────────────────────┤ 客户: 王五    │
│ 流转时间线                           │ 组织: 示例公司│
│                                     │ 渠道: web    │
│ ● pending  09:00                    │              │
│ │                                   │ SLA          │
│ ● open     10:00  操作人：李（对接人）│ 首响: 1h     │
│ │                                   │ 解决: 4h     │
│ ● 追加信息  10:30                   │              │
│ │ 补充截图                          │ 关联工单      │
│ ● on_hold  11:00  原因：等客户反馈   │ ↔ TKT-00038 │
│ │                                   │              │
│ ● resolved 14:00                    │ 创建: 09:00  │
│   处理说明：已修复                   │ 更新: 14:00  │
│   操作人：张三                      │              │
├─────────────────────────────────────┤              │
│ 处理说明 / 追加 编辑器               │              │
│ ┌─────────────────────────────────┐ │              │
│ │ [处理说明] [追加]               │ │              │
│ │ 输入处理说明...                  │ │              │
│ │ [暂缓处理] [提交处理说明]       │ │              │
│ └─────────────────────────────────┘ │              │
└─────────────────────────────────────┴──────────────┘
```

- 状态不再支持手动变更，通过操作自动流转
- 流转时间线位于主栏顶部，按时间顺序展示状态节点、追加节点、处理说明
- 待受理工单（pending）且当前用户为部门对接人时，显示「指派处理人」卡片
- 处理中工单（open）且当前用户为处理人时，可「提交处理说明」或「暂缓处理」
- 内部备注功能已移除

**TicketListView**

```
┌─────────────────────────────────────────────────────┐
│ 筛选栏                                               │
│ [状态 ▼] [优先级 ▼] [客服组 ▼] [负责人 ▼] [搜索...]  │
├───────┬──────────────────┬────┬──────┬──────┬───────┤
│ 编号   │ 标题             │状态│优先级│负责人 │ 更新   │
├───────┼──────────────────┼────┼──────┼──────┼───────┤
│TKT-042│登录页面无法访问    │open│🔴high│张三  │ 5m ago│
│TKT-041│订单查询报错        │new │🟢norm│ —   │ 1h ago│
│TKT-039│密码重置失败 ⚠️SLA │pend│🔴urg │李四  │ 2h ago│
├───────┴──────────────────┴────┴──────┴──────┴───────┤
│                  [< 1  2  3  4  5 >]                │
└─────────────────────────────────────────────────────┘
```

## 4. 状态管理（Pinia Stores）

### 4.1 authStore

```typescript
interface AuthState {
  accessToken: string | null
  refreshToken: string | null
  user: User | null
}

// Actions
login(email, password)    → 调用 API → 存储 token + user
logout()                  → 清除 token → 跳转 /login
refreshToken()            → 调用 refresh API → 更新 accessToken
```

Token 持久化：存储到 `localStorage`，页面刷新时从 localStorage 恢复。

### 4.2 ticketStore

```typescript
interface TicketState {
  tickets: Ticket[]
  currentTicket: TicketDetail | null
  filters: TicketFilters
  pagination: Pagination
  loading: boolean
}

// Actions
fetchTickets(filters, page)    → GET /tickets
fetchTicketDetail(id)          → GET /tickets/{id} + articles + state-logs
createTicket(data)             → POST /tickets
updateTicket(id, data)         → PATCH /tickets/{id}
addArticle(ticketId, data)     → POST /tickets/{id}/articles → 成功后重新拉取详情
refreshCurrentInList()         → 用 currentTicket 同步更新 tickets 列表缓存
```

### 4.3 overviewStore

```typescript
interface OverviewState {
  overviews: Overview[]
  currentOverviewTickets: Ticket[]
}

// Actions
fetchOverviews()                    → GET /overviews
fetchOverviewTickets(id, page)      → GET /overviews/{id}/tickets
```

### 4.4 uiStore

```typescript
interface UIState {
  sidebarCollapsed: boolean
  currentOverviewId: number | null
}
```

## 5. API 调用封装

### 5.1 Axios 实例

```typescript
// api/index.ts
const api = axios.create({
  baseURL: '/api/v1',
  timeout: 15000,
})
```

### 5.2 请求拦截器

```
请求发出前：
  1. 从 authStore 读取 accessToken
  2. 设置 Authorization: Bearer <token>
```

### 5.3 响应拦截器

```
响应返回后：
  1. 状态码 200-299 → 直接返回 data
  2. 状态码 401：
     a. 如果不是 refresh 请求 → 尝试 refreshToken()
     b. 刷新成功 → 重试原请求
     c. 刷新失败 → logout() → 跳转 /login
  3. 其他错误 → ElMessage.error(message)
```

### 5.4 API 模块示例

```typescript
// api/tickets.ts
export const ticketApi = {
  list: (params: TicketListParams) =>
    api.get<PaginatedResponse<Ticket>>('/tickets', { params }),

  get: (id: number) =>
    api.get<TicketDetail>(`/tickets/${id}`),

  create: (data: TicketCreatePayload) =>
    api.post<Ticket>('/tickets', data),

  update: (id: number, data: TicketUpdatePayload) =>
    api.put<Ticket>(`/tickets/${id}`, data),

  getArticles: (ticketId: number) =>
    api.get<Article[]>(`/tickets/${ticketId}/articles`),

  addArticle: (ticketId: number, data: ArticleCreatePayload) =>
    api.post<Article>(`/tickets/${ticketId}/articles`, data),
}
```

## 6. 组件拆分

### 6.1 组件层级

```
App.vue
├── layouts/
│   ├── DefaultLayout.vue        # Agent/Admin 主布局
│   │   ├── TheSidebar.vue       # 侧边栏导航
│   │   └── TheTopbar.vue        # 顶部栏（搜索 + 用户菜单）
│   ├── CustomerLayout.vue       # Customer 简化布局
│   └── AuthLayout.vue           # 登录页布局
│
├── views/                       # 路由页面组件（不复用）
│   ├── DashboardView.vue
│   ├── TicketListView.vue
│   ├── TicketDetailView.vue
│   ├── TicketCreateView.vue
│   ├── SearchView.vue
│   └── admin/*.vue
│
└── components/                  # 可复用组件
    ├── ticket/
    │   ├── ArticleTimeline.vue  # Article 时间线列表
    │   ├── ArticleItem.vue      # 单条 Article 卡片
    │   ├── TicketInfoSidebar.vue# 工单详情右侧信息栏
    │   ├── TicketFilters.vue    # 筛选条件栏
    │   ├── TicketTable.vue      # 工单表格
    │   └── ReplyEditor.vue      # 回复/备注编辑器
    │
    └── common/
        ├── StateTag.vue         # 状态标签（彩色 Tag）
        ├── PriorityIcon.vue     # 优先级图标
        ├── UserAvatar.vue       # 用户头像 + 名字
        ├── SLAIndicator.vue     # SLA 进度条/倒计时
        ├── RelativeTime.vue     # 相对时间显示（"5 分钟前"）
        └── ConfirmDialog.vue    # 通用确认弹窗
```

### 6.2 关键组件说明

| 组件 | Props | 事件 | 说明 |
|---|---|---|---|
| `ArticleTimeline` | `articles: Article[]` | — | 纵向时间线，区分 customer/agent/system/internal |
| `ArticleItem` | `article: Article` | — | 单条对话卡片，内部备注显示锁图标+灰色背景 |
| `ReplyEditor` | `ticketId: number` | `@submitted` | Tab 切换回复/内部备注，提交后清空 |
| `TicketInfoSidebar` | `ticket: TicketDetail` | `@updated` | 可内联编辑状态、优先级、负责人、组 |
| `SLAIndicator` | `escalationAt: string`, `totalMinutes: number` | — | 进度条 + 剩余时间，接近超时变红 |
| `StateTag` | `state: TicketState` | — | 根据 state_type 显示不同颜色 |
| `TicketFilters` | `modelValue: Filters` | `@update:modelValue` | 筛选条件变更后触发工单列表刷新 |

## 7. TypeScript 类型定义

```typescript
// types/index.ts（核心类型摘要）

interface User {
  id: number
  email: string
  firstname: string
  lastname: string
  role: Role
  groups?: Group[]
  organization?: Organization
  active: boolean
}

interface Ticket {
  id: number
  number: string
  title: string
  state: TicketState
  priority: TicketPriority
  group: Group
  owner: User | null
  customer: User
  organization: Organization | null
  channel: 'web' | 'email'
  escalation_at: string | null
  article_count: number
  created_at: string
  updated_at: string
}

interface Article {
  id: number
  ticket_id: number
  origin_by: User
  sender_type: 'agent' | 'customer' | 'system'
  article_type: 'note' | 'email' | 'web' | 'phone'
  body: string
  content_type: 'text/plain' | 'text/html'
  internal: boolean
  created_at: string
}

interface PaginatedResponse<T> {
  data: T[]
  pagination: {
    page: number
    per_page: number
    total: number
    total_pages: number
  }
}
```
