# 00 项目总览（Overview）

## 1. 项目名称
**Skdy Ticket System** —— 轻量级客服工单系统 MVP。

## 2. 一句话愿景
为中小团队提供一个"以对话线程为核心"的客服工单系统，覆盖工单创建、流转、回复、分配、SLA、自动化和邮件渠道接入，开箱可用、易于二次开发。

## 3. 设计参考
本项目核心抽象**借鉴 Zammad**：以 `Ticket + Article（对话条目）` 为骨架，状态机/SLA/触发器是附属能力。详见 `zammad_analysis_notes.md`。

但 MVP **不照搬** Zammad 的体量和复杂度，而是抽出最核心的领域模型，做出一个干净、可扩展的最小可用系统。

## 4. MVP 范围（In-Scope）

| 模块 | 内容 |
|---|---|
| 用户与权限 | User、Role、Group，基于角色的访问控制（RBAC） |
| 认证 | JWT（access + refresh），密码登录 |
| 工单核心 | Ticket CRUD、Article 追加、状态机、优先级、分配 |
| 工单视图 | Overview（保存的查询，如"我的待处理"） |
| 工单关联 | Link（工单↔工单，parent/child/related） |
| SLA | 简化版：first_response_time、solution_time，超时标记 |
| 自动化 | Trigger（条件→动作），如新工单自动分配 |
| 渠道 | Web（默认）+ Email（IMAP 收件 → 自动建单/追加 Article） |
| 通知 | 邮件通知（新工单分配、被 @、状态变化） |
| 前端 | Vue 3 极简 SPA：登录、列表、详情、新建、回复 |
| 部署 | Docker Compose 一键启动 |

## 5. 非目标（Out-of-Scope）

明确**不做**的事，避免范围蔓延：

- 多租户严格数据隔离（合规级）
- 知识库（KB）
- 复杂表单引擎、BPMN 审批流
- 实时聊天（WebSocket 推送）—— 仅作为 V2 候选
- 项目管理（看板、Sprint、Story Point）
- 移动端 App
- 国际化多语言（默认中文）
- 信创/国产化适配（V2 再考虑）

## 6. 关键决策

| 决策点 | 选择 | 理由 |
|---|---|---|
| 后端语言 | Python 3.11 | 团队偏好，FastAPI 生态成熟 |
| Web 框架 | FastAPI | 异步原生、OpenAPI 自动生成、类型注解友好 |
| ORM | SQLAlchemy 2.0 | 成熟稳定，async 支持完善 |
| 数据库 | PostgreSQL 15 | JSONB、丰富索引、全文检索原生支持 |
| 缓存/队列 | Redis 7 | 同时承担缓存、ARQ 队列、限流 |
| 异步任务 | ARQ | asyncio 原生，比 Celery 轻量，与 FastAPI 同栈 |
| 迁移 | Alembic | SQLAlchemy 标配 |
| 认证 | JWT (HS256) | 无状态、易扩展 |
| 前端框架 | Vue 3 + TypeScript | 上手快、Element Plus 组件齐全 |
| 构建工具 | Vite | 启动快、HMR 体验好 |
| 容器化 | Docker Compose | 一键启动 app + db + redis |

## 7. 术语表（Glossary）

| 术语 | 定义 |
|---|---|
| **Ticket（工单）** | 一次客户请求的容器，承载状态、优先级、归属、关联人 |
| **Article（条目）** | 工单内的一条对话记录（来信、回复、内部备注） |
| **User（用户）** | 系统账号，可以是 Agent（客服）或 Customer（客户） |
| **Group（组）** | 客服队列，工单归属到组，Agent 通过组获得访问权 |
| **Role（角色）** | 权限的命名集合（admin/agent/customer） |
| **State（状态）** | 工单状态（new/open/pending/resolved/closed） |
| **Priority（优先级）** | low/normal/high/urgent |
| **Channel（渠道）** | 工单的来源（web/email），后续可扩展 |
| **Trigger（触发器）** | 基于条件的事件驱动自动化（条件→动作） |
| **SLA** | Service Level Agreement，承诺的响应/解决时限 |
| **Overview（视图）** | 保存的查询条件，给 Agent 提供工单分组面板 |

## 8. 成功标准

MVP 验收时应满足：
1. 客户可通过 Web/邮件提交工单，客服收到通知。
2. 客服可在前端完成"分配 → 回复 → 关闭"的完整工单生命周期。
3. SLA 超时的工单在列表中有视觉标记，并触发邮件提醒。
4. 至少 1 条 Trigger 规则（如"新工单自动分配到默认组"）能正常运行。
5. `docker-compose up` 后，10 分钟内完成端到端冒烟测试。
6. 后端测试覆盖率 ≥ 70%（核心领域逻辑）。
