# 01 需求规格（Requirements）

## 1. 角色定义

| 角色 | 描述 | 关键权限 |
|---|---|---|
| **Admin（管理员）** | 系统管理员 | 全部权限，配置 Group/Role/Trigger/SLA |
| **Agent（客服）** | 处理工单的人 | 查看与处理所属 Group 的工单；可回访/归档/退回 |
| **Handler（部门对接人）** | 技能组对接人 | 分派待受理工单给处理人；可撤销工单 |
| **Customer（客户）** | 提交工单的人 | 仅查看与回复自己提交的工单 |

## 2. 用户故事（Functional Requirements）

### 2.1 认证与账户（Auth）

- **F-AUTH-01** 作为用户，我可以用邮箱+密码登录，获取 access_token 和 refresh_token。
- **F-AUTH-02** 作为用户，access_token 过期时我可以用 refresh_token 续签。
- **F-AUTH-03** 作为 Admin，我可以创建/禁用 User 账号，分配 Role 和 Group。
- **F-AUTH-04** 作为用户，我可以修改自己的密码。

### 2.2 工单生命周期（Ticket Lifecycle）

- **F-TKT-01** 作为 Customer，我可以通过 Web 表单提交工单（标题、内容、优先级建议）。
- **F-TKT-02** 作为 Agent/Handler，我可以查看分配给我所在 Group 的工单列表，支持按状态/优先级/创建时间筛选与分页。
- **F-TKT-03** 作为 Agent/Handler，我可以查看工单详情（含流转时间线、处理说明、追加记录）。
- **F-TKT-04** 作为 Handler（部门对接人），我可以将待受理工单分派给某个处理人（owner）。
- **F-TKT-05** 系统应根据操作自动变更工单状态（如分派后进入处理中、处理人提交处理说明后进入已处理、暂缓后进入暂缓处理），不再提供手动状态变更入口。
- **F-TKT-06** 作为 Agent，我可以变更工单优先级。
- **F-TKT-07** 作为 Agent/Handler/Customer，我可以在工单上追加 Article（处理说明、追加、系统提醒）；内部备注功能已移除。
- **F-TKT-08** 作为 Agent，我可以将一个工单标记为另一个工单的子单/相关单（Link）。
- **F-TKT-09** 作为 Agent，我可以将两个重复工单合并（merge）。
- **F-TKT-10** 作为处理人（owner），我可以在处理中/暂缓处理状态下提交「处理说明」，系统自动将工单置为「已处理」。
- **F-TKT-11** 作为处理人（owner），我可以在处理中状态下选择「暂缓处理」，填写原因后工单进入「暂缓处理」状态，处理人保持不变。
- **F-TKT-12** 作为 Agent，我可以在已处理状态下进行回访/归档/退回操作。

### 2.3 视图与检索（Overview & Search）

- **F-OV-01** 作为 Agent，我可以在仪表盘看到内置 Overview：「我的待处理」「我所在组未分配」「逾期工单」。
- **F-OV-02** 作为 Admin，我可以配置自定义 Overview（保存查询条件）。
- **F-SR-01** 作为用户，我可以按关键字搜索工单标题与正文（PostgreSQL 全文检索）。

### 2.4 SLA

- **F-SLA-01** 作为 Admin，我可以为某个 Group + 优先级 配置 SLA：first_response_time、solution_time。
- **F-SLA-02** 系统应在工单创建/状态变更时计算 escalation_at 时间戳。
- **F-SLA-03** 工单接近 SLA 截止时（剩余 < 20%）应在列表中以颜色标记。
- **F-SLA-04** SLA 超时时应触发邮件通知（owner + group 主管）。

### 2.5 自动化（Triggers）

- **F-TRG-01** 作为 Admin，我可以配置 Trigger：「当 X 条件 → 执行 Y 动作」。
- **F-TRG-02** 支持的条件：state、priority、group、是否首次客户回复、关键字匹配。
- **F-TRG-03** 支持的动作：分配 owner/group、变更状态、变更优先级、发送通知邮件。
- **F-TRG-04** Trigger 应在 ticket/article 的 create/update 后异步执行。

### 2.6 邮件渠道（Email Channel）

- **F-EM-01** 作为 Admin，我可以配置一个 IMAP 邮箱作为收件渠道，绑定到默认 Group。
- **F-EM-02** 系统应定时（默认 60s）拉取邮件，新邮件创建工单（subject→title，body→Article）。
- **F-EM-03** 回信中包含工单号（如 `[Ticket#1234]`）的邮件应追加 Article 到原工单，而非新建。
- **F-EM-04** 系统通过 SMTP 发送通知邮件，发件主题包含 `[Ticket#1234]` 用于回信识别。

### 2.7 通知（Notifications）

- **F-NT-01** 工单被分配给 Agent 时，发邮件通知该 Agent。
- **F-NT-02** 工单有新 Article（来自客户/对方角色）时，发邮件通知 owner。
- **F-NT-03** 工单状态变为 resolved 时，发邮件通知 customer。

## 3. 非功能性需求（Non-Functional）

### 3.1 性能
- **N-PERF-01** 工单列表 API（分页 50 条）p95 < 300ms（数据量 10 万工单内）。
- **N-PERF-02** 工单详情 API（含 Article 列表）p95 < 200ms。
- **N-PERF-03** 邮件拉取间隔可配置，默认 60s，单次最多处理 50 封。

### 3.2 安全
- **N-SEC-01** 密码使用 bcrypt 存储（cost ≥ 12）。
- **N-SEC-02** 所有写操作 API 需要 JWT 鉴权。
- **N-SEC-03** Customer 仅能访问自己创建的工单；Agent 仅能访问所在 Group 的工单（行级权限）。
- **N-SEC-04** SQL 注入防御：全部走 ORM 参数化查询。
- **N-SEC-05** 邮件正文渲染前需 HTML 转义（防 XSS）。

### 3.3 可用性
- **N-AVL-01** MVP 单节点部署即可，不要求高可用。
- **N-AVL-02** 数据库需有日备份脚本（V2 自动化）。

### 3.4 可观测性
- **N-OBS-01** 后端结构化日志（JSON）输出到 stdout。
- **N-OBS-02** 关键操作（登录、工单创建、状态变更）记录审计日志。
- **N-OBS-03** 提供 `/healthz` 与 `/readyz` 健康检查端点。

### 3.5 可维护性
- **N-MNT-01** 代码遵循 PEP8 + ruff lint。
- **N-MNT-02** 核心领域逻辑（services 层）测试覆盖率 ≥ 70%。
- **N-MNT-03** 所有 API 自动生成 OpenAPI 文档（FastAPI 内置）。

## 4. 验收用例（Acceptance Scenarios）

**场景 A：客户提交工单 → 对接人分派 → 处理人解决 → 客服关闭**
1. Customer 在 Web 提交工单 "登录失败"
2. 系统创建 Ticket，状态 = pending
3. Handler（部门对接人）登录后台，将工单分派给处理人 Agent
4. 工单状态变为 open，处理人收到通知
5. 处理人提交「处理说明」，系统自动将工单置为 resolved
6. Agent 进行回访后归档，工单关闭

**场景 A-1：处理人暂缓处理**
1. 处理中（open）工单的处理人选择「暂缓处理」
2. 填写暂缓原因后提交，工单状态变为 on_hold
3. 处理人后续继续跟进，提交处理说明后工单进入 resolved

**场景 B：SLA 超时**
1. Group "VIP" 配置 SLA：first_response_time = 1h
2. 创建紧急工单，escalation_at 设为 1h 后
3. 1h 内无回复，定时任务触发，发送超时通知邮件
4. 工单列表中以红色标记
